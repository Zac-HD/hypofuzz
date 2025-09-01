"""Live web dashboard for a fuzzing run."""

import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal, Optional
import socket

import trio
from hypercorn.config import Config
from hypercorn.trio import serve
from hypothesis import settings
from hypothesis.database import (
    ListenerEventT,
)
from starlette.applications import Starlette
from starlette.responses import FileResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import Scope
from trio import MemoryReceiveChannel

from hypofuzz.collection import CollectionResult
from hypofuzz.dashboard.api import api_routes
from hypofuzz.dashboard.models import (
    AddFailuresEvent,
    AddObservationsEvent,
    AddReportsEvent,
    DashboardEventT,
    DashboardFailure,
    SetFailuresEvent,
    SetFatalFailureEvent,
    dashboard_failures,
    dashboard_fatal_failure,
    dashboard_observation,
    dashboard_report,
)
from hypofuzz.dashboard.patching import (
    add_patch,
    start_patching_thread,
)
from hypofuzz.dashboard.test import Test
from hypofuzz.dashboard.websocket import broadcast_event, websocket_routes, websockets
from hypofuzz.database import (
    DatabaseEvent,
    DatabaseEventKey,
    FailureState,
    FatalFailure,
    HypofuzzDatabase,
    Observation,
    ObservationStatus,
    Report,
)
from hypofuzz.hypofuzz import FuzzTarget

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


class DocsStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        # with StaticFiles(..., html=True), you can get /docs/ to load index.html.
        # But I'd like it to *redirect* to index.html, so /docs/ is not confused
        # for the canonical /docs/index/html url.
        if path == ".":
            return RedirectResponse(url=f"{scope['path']}index.html")
        return await super().get_response(path, scope)


async def serve_app(app: Any, host: str, port: str) -> None:
    config = Config()
    config.bind = [f"{host}:{port}"]
    # disable the dashboard url print. We already print it ourselves in a better
    # way
    config.loglevel = "warning"
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
        test_function=target[0].test_fn,
        nodeid=nodeid,
        observation=observation,
        observation_type=observation_type,
    )


def _dashboard_event(db_event: DatabaseEvent) -> Optional[DashboardEventT]:
    event: Optional[DashboardEventT] = None
    if db_event.type == "save":
        value = db_event.value
        assert value is not None

        if db_event.key is DatabaseEventKey.REPORT:
            assert isinstance(value, Report)
            if value.nodeid not in TESTS:
                return None

            TESTS[value.nodeid].add_report(value)
            event = AddReportsEvent(
                nodeid=value.nodeid,
                worker_uuid=value.worker_uuid,
                reports=[dashboard_report(value)],
            )
        elif db_event.key in [
            DatabaseEventKey.FAILURE_SHRUNK_OBSERVATION,
            DatabaseEventKey.FAILURE_UNSHRUNK_OBSERVATION,
        ]:
            assert isinstance(value, Observation)
            if value.property not in TESTS:
                return None

            nodeid = value.property
            state = (
                FailureState.UNSHRUNK
                if db_event.key is DatabaseEventKey.FAILURE_UNSHRUNK_OBSERVATION
                else FailureState.SHRUNK
            )
            event = AddFailuresEvent(
                nodeid=nodeid,
                failures={
                    value.status_reason: DashboardFailure(
                        state=state, observation=dashboard_observation(value)
                    )
                },
            )
            TESTS[nodeid].failures[value.status_reason] = (state, value)
            _add_patch(nodeid, value, "failing")
        elif db_event.key is DatabaseEventKey.ROLLING_OBSERVATION:
            assert isinstance(value, Observation)
            if value.property not in TESTS:
                return None

            observations = TESTS[value.property].rolling_observations
            # TODO store rolling_observationas as a proper logn sortedlist,
            # probably requires refactoring Test to be a proper class (not a
            # dataclass)
            observations.append(value)
            observations.sort(key=lambda o: -o.run_start)
            TESTS[value.property].rolling_observations = observations[:300]
            event = AddObservationsEvent(
                nodeid=value.property,
                observation_type="rolling",
                observations=[dashboard_observation(value)],
            )
        elif db_event.key is DatabaseEventKey.CORPUS_OBSERVATION:
            assert isinstance(value, Observation)
            if value.property not in TESTS:
                return None

            nodeid = value.property
            TESTS[nodeid].corpus_observations.append(value)
            _add_patch(nodeid, value, "covering")
            event = AddObservationsEvent(
                nodeid=nodeid,
                observation_type="corpus",
                observations=[dashboard_observation(value)],
            )
        elif db_event.key is DatabaseEventKey.FAILURE_FATAL:
            assert isinstance(value, FatalFailure)
            if value.nodeid not in TESTS:
                return None

            TESTS[value.nodeid].fatal_failure = value
            event = SetFatalFailureEvent(
                nodeid=value.nodeid,
                fatal_failure=dashboard_fatal_failure(value),
            )
        else:
            return None
    elif db_event.type == "delete":
        if db_event.key in [
            DatabaseEventKey.FAILURE_SHRUNK_OBSERVATION,
            DatabaseEventKey.FAILURE_UNSHRUNK_OBSERVATION,
        ]:
            if db_event.database_key not in TESTS_BY_KEY:
                return None
            # we know a failure was just deleted from this test, but not which
            # one (unless the database supports value deletion). Re-scan its
            # failures.
            test = TESTS_BY_KEY[db_event.database_key]
            assert test.database_key_bytes == db_event.database_key
            failure_observations = get_failures(db_event.database_key)
            test.failures = failure_observations
            event = SetFailuresEvent(
                nodeid=test.nodeid, failures=dashboard_failures(failure_observations)
            )
        elif db_event.key is DatabaseEventKey.FAILURE_FATAL:
            test = TESTS_BY_KEY[db_event.database_key]
            test.fatal_failure = None
            event = SetFatalFailureEvent(
                nodeid=test.nodeid,
                fatal_failure=None,
            )
        else:
            return None
    else:
        raise ValueError(f"Unknown database event type: {db_event.type}")

    return event


async def handle_event(receive_channel: MemoryReceiveChannel[ListenerEventT]) -> None:
    global LOADING_STATE

    async for listener_event in receive_channel:
        db_event = DatabaseEvent.from_event(listener_event)
        # In the single-command ``hypothesis fuzz`` case, this is a
        # transmission from a worker launched by that command to the
        # dashboard launched by that command. The schemas should never
        # be mismatched in this case.
        #
        # However, in the distributed case, a worker might be running an old
        # hypofuzz version while the dashboard runs a newer version. Here,
        # a None report from a parse error could occur.
        if db_event is None:
            continue

        if not LOADING_STATE.get(db_event.database_key, False):
            # we haven't loaded initial state from this test yet in
            # load_initial_state.
            continue

        event = _dashboard_event(db_event)
        if event is None:
            continue

        await broadcast_event(event)


def get_failures(
    database_key: bytes,
) -> dict[str, tuple[FailureState, Observation]]:
    assert db is not None

    def _failure_observations(
        state: FailureState,
    ) -> dict[str, tuple[FailureState, Observation]]:
        failure_observations: dict[str, tuple[FailureState, Observation]] = {}
        for maybe_observed_choices in sorted(
            db.failures(state=state).fetch(database_key), key=len
        ):
            if observation := db.failure_observations(state=state).fetch(
                database_key, maybe_observed_choices
            ):
                if observation.status is not ObservationStatus.FAILED:
                    # This should never happen, but database corruption *can*.
                    continue  # pragma: no cover
                # For failures, Hypothesis records the interesting_origin string
                # as the status_reason, which is how we dedupe errors upstream.
                if observation.status_reason not in failure_observations:
                    failure_observations[observation.status_reason] = (
                        state,
                        observation,
                    )

        return failure_observations

    # note: we fetch unshrunk failures first, so that a race condition can only
    # result in missing new unshrunk failures, and not a shrunk failure in a
    # transition from unshrunk to shrunk.
    return _failure_observations(FailureState.UNSHRUNK) | _failure_observations(
        FailureState.SHRUNK
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

    rolling_observations = list(db.rolling_observations.fetch(key))
    corpus_observations = [
        db.corpus_observations.fetch(key, choices)
        for choices in db.corpus.fetch(key, as_bytes=True)
    ]
    corpus_observations = [
        observation for observation in corpus_observations if observation is not None
    ]

    reports_by_worker = defaultdict(list)
    for report in sorted(db.reports.fetch(key), key=lambda r: r.elapsed_time):
        reports_by_worker[report.worker_uuid].append(report)

    failures = get_failures(key)
    fatal_failure = db.fatal_failures.fetch(key)

    # backfill our patches for our worker thread to take care of computing
    for _state, observation in failures.values():
        _add_patch(fuzz_target.nodeid, observation, "failing")
    for observation in corpus_observations:
        _add_patch(fuzz_target.nodeid, observation, "covering")
    test = Test(
        database_key=fuzz_target.database_key_str,
        nodeid=fuzz_target.nodeid,
        rolling_observations=rolling_observations,
        corpus_observations=corpus_observations,
        # we're abusing this argument rn. post-init the reports have type
        # ReportWithDiff, but at pre-init they have type Report. We should
        # split this into two attributes, one for Report which we pass at init
        # and one for ReportWithDiff which is set/stored post-init.
        reports_by_worker=reports_by_worker,  # type: ignore
        failures=failures,
        fatal_failure=fatal_failure,
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
    port: int,
    *,
    pytest_args: list,
    host: str = "localhost",
    print_status: bool = False,
) -> None:
    from hypofuzz.collection import collect_tests

    global COLLECTION_RESULT
    global db

    # we run a pytest collection step for the dashboard to pick up on the database
    # from any custom profiles, and as a ground truth for what tests to display.
    if print_status:
        print("collecting tests... ", end="", flush=True)
    COLLECTION_RESULT = collect_tests(pytest_args)
    if print_status:
        print("done")
    db = HypofuzzDatabase(settings().database)

    start_patching_thread()

    if port == 0:
        # we would normally let hypercorn choose the port here via the standard
        # port=0 mechanism, but then we wouldn't be able to print it.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, 0))
            port = s.getsockname()[1]

    print(f"\n\tNow serving dashboard at http://{host}:{port}/\n", flush=True)
    trio.run(run_dashboard, port, host)


dist = Path(__file__).parent.parent / "frontend" / "dist"
dist.mkdir(exist_ok=True)
routes = [
    *websocket_routes,
    *api_routes,
    Mount("/assets", StaticFiles(directory=dist / "assets")),
    # StaticFiles only matches /docs/, not /docs, for some reason
    Route("/docs", lambda request: RedirectResponse(url="/docs/")),
    Mount("/docs", DocsStaticFiles(directory=dist / "docs")),
    Mount("/favicon", StaticFiles(directory=dist / "favicon")),
    # catchall fallback. react will handle the routing of dynamic urls here,
    # such as to a node id. This also includes the 404 page.
    Route("/{path:path}", FileResponse(dist / "index.html")),
]
app = Starlette(routes=routes)
