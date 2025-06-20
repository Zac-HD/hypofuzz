"""Live web dashboard for a fuzzing run."""

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal, Optional

import black
import trio
from hypercorn.config import Config
from hypercorn.trio import serve
from hypothesis import settings
from hypothesis.database import (
    ListenerEventT,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.types import Scope
from trio import MemoryReceiveChannel

from hypofuzz.collection import CollectionResult
from hypofuzz.dashboard.models import (
    dashboard_observation,
    dashboard_report,
    dashboard_test,
)
from hypofuzz.dashboard.patching import (
    add_patch,
    covering_patch,
    failing_patch,
    start_patching_thread,
)
from hypofuzz.dashboard.test import Test
from hypofuzz.dashboard.websocket import broadcast_event, websocket_route, websockets
from hypofuzz.database import (
    DatabaseEvent,
    DatabaseEventKey,
    FailureState,
    HypofuzzDatabase,
    HypofuzzEncoder,
    Observation,
    ObservationStatus,
)
from hypofuzz.hypofuzz import FuzzTarget
from hypofuzz.utils import convert_to_fuzzjson

# these two test dicts always contain the same values, just with different access
# keys

# nodeid: Test
TESTS: dict[str, "Test"] = {}
# database_key: Test
TESTS_BY_KEY: dict[bytes, "Test"] = {}
# databse_key: loaded
LOADING_STATE: dict[bytes, bool] = {}
COLLECTION_RESULT: Optional[CollectionResult] = None
db: Optional[HypofuzzDatabase] = None


class HypofuzzJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        data = json.dumps(
            convert_to_fuzzjson(content),
            ensure_ascii=False,
            separators=(",", ":"),
            cls=HypofuzzEncoder,
        )
        return data.encode("utf-8", errors="surrogatepass")


def try_format(code: str) -> str:
    try:
        return black.format_str(code, mode=black.FileMode())
    except Exception:
        return code


async def api_tests(request: Request) -> Response:
    return HypofuzzJSONResponse(
        {nodeid: dashboard_test(test) for nodeid, test in TESTS.items()}
    )


async def api_test(request: Request) -> Response:
    nodeid = request.path_params["nodeid"]
    return HypofuzzJSONResponse(dashboard_test(TESTS[nodeid]))


def _patches() -> dict[str, dict[str, Optional[str]]]:
    assert COLLECTION_RESULT is not None
    return {
        target.nodeid: {
            "failing": failing_patch(target.nodeid),
            "covering": covering_patch(target.nodeid),
        }
        for target in COLLECTION_RESULT.fuzz_targets
    }


async def api_patches(request: Request) -> Response:
    return HypofuzzJSONResponse(_patches())


async def api_available_patches(request: Request) -> Response:
    # returns the nodeids with available patches
    from hypofuzz.dashboard.patching import PATCHES

    nodeids = [
        nodeid
        for nodeid, patches in PATCHES.items()
        if patches["failing"] or patches["covering"]
    ]
    return HypofuzzJSONResponse(nodeids)


async def api_patch(request: Request) -> Response:
    assert COLLECTION_RESULT is not None
    nodeid = request.path_params["nodeid"]
    if nodeid not in TESTS:
        return Response(status_code=404)

    return HypofuzzJSONResponse(
        {"failing": failing_patch(nodeid), "covering": covering_patch(nodeid)}
    )


def _collection_status() -> list[dict[str, Any]]:
    assert COLLECTION_RESULT is not None

    collection_status = [
        {"nodeid": target.nodeid, "status": "collected"}
        for target in COLLECTION_RESULT.fuzz_targets
    ]
    for nodeid, item in COLLECTION_RESULT.not_collected.items():
        collection_status.append(
            {
                "nodeid": nodeid,
                "status": "not_collected",
                "status_reason": item["status_reason"],
            }
        )
    return collection_status


async def api_collected_tests(request: Request) -> Response:
    return HypofuzzJSONResponse({"collection_status": _collection_status()})


# get the backing state of the dashboard, suitable for use by dashboard_state/*.json.
async def api_backing_state_tests(request: Request) -> Response:
    tests = {
        nodeid: {
            "database_key": test.database_key,
            "nodeid": test.nodeid,
            "failure": test.failure,
            "reports_by_worker": {
                worker_uuid: [dashboard_report(report) for report in reports]
                for worker_uuid, reports in test.reports_by_worker.items()
            },
        }
        for nodeid, test in TESTS.items()
    }
    return HypofuzzJSONResponse(tests)


async def api_backing_state_observations(request: Request) -> Response:
    observations = {
        nodeid: {
            "rolling": [
                dashboard_observation(obs) for obs in test.rolling_observations
            ],
            "corpus": [dashboard_observation(obs) for obs in test.corpus_observations],
        }
        for nodeid, test in TESTS.items()
    }
    return HypofuzzJSONResponse(observations)


async def api_backing_state_api(request: Request) -> Response:
    return HypofuzzJSONResponse(
        {
            "collected_tests": {"collection_status": _collection_status()},
            "patches": _patches(),
        }
    )


class DocsStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        # with StaticFiles(..., html=True), you can get /docs/ to load index.html.
        # But I'd like it to *redirect* to index.html, so /docs/ is not confused
        # for the canonical /docs/index/html url.
        if path == ".":
            return RedirectResponse(url=f"{scope['path']}index.html")
        return await super().get_response(path, scope)


dist = Path(__file__).parent.parent / "frontend" / "dist"
dist.mkdir(exist_ok=True)
routes = [
    WebSocketRoute("/ws", websocket_route),
    Route("/api/tests/", api_tests),
    Route("/api/tests/{nodeid:path}", api_test),
    Route("/api/patches/{nodeid:path}", api_patch),
    Route("/api/available_patches/", api_available_patches),
    Route("/api/collected_tests/", api_collected_tests),
    Route("/api/backing_state/tests", api_backing_state_tests),
    Route("/api/backing_state/observations", api_backing_state_observations),
    Route("/api/backing_state/api", api_backing_state_api),
    Mount("/assets", StaticFiles(directory=dist / "assets")),
    # StaticFiles only matches /docs/, not /docs, for some reason
    Route("/docs", lambda request: RedirectResponse(url="/docs/")),
    Mount("/docs", DocsStaticFiles(directory=dist / "docs")),
    # catchall fallback. react will handle the routing of dynamic urls here,
    # such as to a node id. This also includes the 404 page.
    Route("/{path:path}", FileResponse(dist / "index.html")),
]
app = Starlette(routes=routes)


async def serve_app(app: Any, host: str, port: str) -> None:
    config = Config()
    config.bind = [f"{host}:{port}"]
    await serve(app, config)


def _add_patch(
    nodeid: str,
    observation: Observation,
    observation_type: Literal["covering", "failing"],
) -> None:
    assert COLLECTION_RESULT is not None
    target = [
        target for target in COLLECTION_RESULT.fuzz_targets if target.nodeid == nodeid
    ]
    assert len(target) == 1
    add_patch(
        test_function=target[0]._test_fn,
        nodeid=nodeid,
        observation=observation,
        observation_type=observation_type,
    )


async def handle_event(receive_channel: MemoryReceiveChannel[ListenerEventT]) -> None:
    global LOADING_STATE

    async for listener_event in receive_channel:
        event = DatabaseEvent.from_event(listener_event)
        # In the single-command ``hypothesis fuzz`` case, this is a
        # transmission from a worker launched by that command to the
        # dashboard launched by that command. The schemas should never
        # be mismatched in this case.
        #
        # However, in the distributed case, a worker might be running an old
        # hypofuzz version while the dashboard runs a newer version. Here,
        # a None report from a parse error could occur.
        if event is None:
            continue

        if not LOADING_STATE.get(event.database_key, False):
            # we haven't loaded initial state from this test yet in
            # load_initial_state.
            continue

        if event.type == "save":
            assert event.value is not None

            if event.key is DatabaseEventKey.REPORT:
                if event.value.nodeid not in TESTS:
                    continue
                TESTS[event.value.nodeid].add_report(event.value)
            elif event.key in [
                DatabaseEventKey.FAILURE_SHRUNK_OBSERVATION,
                DatabaseEventKey.FAILURE_UNSHRUNK_OBSERVATION,
            ]:
                if event.value.property not in TESTS:
                    continue
                nodeid = event.value.property
                TESTS[nodeid].failure = event.value
                _add_patch(nodeid, event.value, "failing")
            elif event.key is DatabaseEventKey.ROLLING_OBSERVATION:
                if event.value.property not in TESTS:
                    continue
                observations = TESTS[event.value.property].rolling_observations
                # TODO store rolling_observationas as a proper logn sortedlist,
                # probably requires refactoring Test to be a proper class
                observations.append(event.value)
                observations.sort(key=lambda o: -o.run_start)
                TESTS[event.value.property].rolling_observations = observations[:300]
            elif event.key is DatabaseEventKey.CORPUS_OBSERVATION:
                if event.value.property not in TESTS:
                    continue
                nodeid = event.value.property
                TESTS[nodeid].corpus_observations.append(event.value)
                _add_patch(nodeid, event.value, "covering")

            await broadcast_event(event.type, event.key, event.value)

        # we're handling deletion events in a customish way, since event.value is
        # always None for databases which don't support value deletion. The value
        # we send to the websocket .on_event method is computed here and is specific
        # to each event type.
        if event.type == "delete":
            if event.key in [
                DatabaseEventKey.FAILURE_SHRUNK_OBSERVATION,
                DatabaseEventKey.FAILURE_UNSHRUNK_OBSERVATION,
            ]:
                if event.database_key not in TESTS_BY_KEY:
                    continue
                # we know a failure was just deleted from this test, but not which
                # one (unless the database supports value deletion). Re-scan its
                # failures.
                test = TESTS_BY_KEY[event.database_key]
                assert test.database_key_bytes == event.database_key
                failure_observations = get_failure_observations(event.database_key)
                if not failure_observations.values():
                    previous_failure = test.failure
                    test.failure = None
                    await broadcast_event(
                        "delete",
                        # this event type isn't quite right (we don't know it's
                        # shrunk vs unshrunk), but the dashboard doesn't know
                        # the different for now. TODO refactor properly when we
                        # display shrinking state / multiple failures
                        DatabaseEventKey.FAILURE_SHRUNK_OBSERVATION,
                        previous_failure,
                    )


def get_failure_observations(database_key: bytes) -> dict[str, Observation]:
    assert db is not None

    def _failure_observations(state: FailureState) -> dict[str, Observation]:
        failure_observations: dict[str, Observation] = {}
        for maybe_observed_choices in sorted(
            db.fetch_failures(database_key, state=state), key=len
        ):
            if observation := db.fetch_failure_observation(
                database_key, maybe_observed_choices, state=state
            ):
                if observation.status is not ObservationStatus.FAILED:
                    # This should never happen, but database corruption *can*.
                    continue  # pragma: no cover
                # For failures, Hypothesis records the interesting_origin string
                # as the status_reason, which is how we dedupe errors upstream.
                if observation.status_reason not in failure_observations:
                    failure_observations[observation.status_reason] = observation

        return failure_observations

    return _failure_observations(FailureState.SHRUNK) | _failure_observations(
        FailureState.UNSHRUNK
    )


def _load_initial_state(fuzz_target: FuzzTarget) -> None:
    assert COLLECTION_RESULT is not None
    assert db is not None
    # a fuzz target (= node id) may have many database keys over time as the
    # source code of the test changes. Show only reports from the latest
    # database key = source code version.
    #
    # We may eventually want to track the database_key history of a node id
    # and at least transfer its covering corpus across when we detect a migration,
    # as well as possibly showing a history ui in the dashboard.
    # (maybe use test_keys_key for this?)
    key = fuzz_target.database_key

    rolling_observations = list(db.fetch_observations(key))
    corpus_observations = [
        db.fetch_corpus_observation(key, choices)
        for choices in db.fetch_corpus(key, as_bytes=True)
    ]
    corpus_observations = [
        observation for observation in corpus_observations if observation is not None
    ]

    reports_by_worker = defaultdict(list)
    for report in sorted(db.fetch_reports(key), key=lambda r: r.elapsed_time):
        reports_by_worker[report.worker_uuid].append(report)

    failure_observations = get_failure_observations(key)

    # backfill our patches for our worker thread to take care of computing
    for observation in failure_observations.values():
        _add_patch(fuzz_target.nodeid, observation, "failing")
    for observation in corpus_observations:
        _add_patch(fuzz_target.nodeid, observation, "covering")

    test = Test(
        database_key=fuzz_target.database_key_str,
        nodeid=fuzz_target.nodeid,
        rolling_observations=rolling_observations,
        corpus_observations=corpus_observations,
        # we're abusing this argument, post-init the reports have type
        # ReportWithDiff, but at pre-init they have type Report. We should
        # split this into two attributes, one for Report which we pass at init
        # and one for ReportWithDiff which is set/stored post-init.
        reports_by_worker=reports_by_worker,  # type: ignore
        # TODO: refactor Test, and our frontend, to support multiple failures.
        failure=next(iter(failure_observations.values()), None),
    )
    TESTS[fuzz_target.nodeid] = test
    TESTS_BY_KEY[fuzz_target.database_key] = test


async def load_initial_state(fuzz_target: FuzzTarget) -> None:
    global LOADING_STATE

    await trio.to_thread.run_sync(_load_initial_state, fuzz_target)

    assert fuzz_target.nodeid in TESTS
    test = TESTS[fuzz_target.nodeid]
    LOADING_STATE[fuzz_target.database_key] = True

    for websocket in websockets.copy():
        # TODO: make this more granular? So we send incremental batches
        # of reports as they're loaded, etc. Would need trio.from_thread inside
        # _load_initial_state.
        await websocket.send_tests({test.nodeid: test})


async def run_dashboard(port: int, host: str) -> None:
    assert COLLECTION_RESULT is not None
    assert db is not None

    send_channel, receive_channel = trio.open_memory_channel[ListenerEventT](math.inf)
    trio_token = trio.lowlevel.current_trio_token()

    def send_nowait_from_anywhere(event: ListenerEventT) -> None:
        # DirectoryBasedExampleDatabase sends events from a background thread (via watchdog),
        # so we need to support sending from anywhere, i.e. whether or not the calling thread
        # has any Trio state.  We can do that with the following branch:
        try:
            trio.lowlevel.current_task()
        except RuntimeError:
            trio.from_thread.run_sync(
                send_channel.send_nowait, event, trio_token=trio_token
            )
        else:
            send_channel.send_nowait(event)

    # Any database events that get submitted while we're computing initial state
    # won't be displayed until a dashboard restart. We could solve this by adding the
    # listener first, then storing reports in a queue, to be resolved after
    # computing initial state.
    #
    # For now this is an acceptable loss.
    db._db.add_listener(send_nowait_from_anywhere)

    async with trio.open_nursery() as nursery:
        for fuzz_target in COLLECTION_RESULT.fuzz_targets:
            nursery.start_soon(load_initial_state, fuzz_target)

        nursery.start_soon(serve_app, app, host, port)  # type: ignore
        nursery.start_soon(handle_event, receive_channel)


def start_dashboard_process(
    port: int, *, pytest_args: list, host: str = "localhost"
) -> None:
    from hypofuzz.collection import collect_tests

    global COLLECTION_RESULT
    global db

    # we run a pytest collection step for the dashboard to pick up on the database
    # from any custom profiles, and as a ground truth for what tests to display.
    COLLECTION_RESULT = collect_tests(pytest_args)
    db = HypofuzzDatabase(settings().database)

    start_patching_thread()

    print(f"\n\tNow serving dashboard at  http://{host}:{port}/\n")
    trio.run(run_dashboard, port, host)
