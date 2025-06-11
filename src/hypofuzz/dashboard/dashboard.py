"""Live web dashboard for a fuzzing run."""

import abc
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
from starlette.websockets import WebSocket, WebSocketDisconnect
from trio import MemoryReceiveChannel

from hypofuzz.dashboard.models import (
    AddReportsEvent,
    AddTestsEvent,
    DashboardEventT,
    DashboardEventType,
    dashboard_observation,
    dashboard_report,
    dashboard_test,
)
from hypofuzz.dashboard.patching import make_and_save_patches
from hypofuzz.dashboard.test import Test
from hypofuzz.database import (
    DatabaseEvent,
    DatabaseEventKey,
    HypofuzzDatabase,
    HypofuzzEncoder,
    Observation,
    ObservationStatus,
    Report,
    ReportWithDiff,
)
from hypofuzz.hypofuzz import FuzzProcess
from hypofuzz.interface import CollectionResult
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
websockets: set["HypofuzzWebsocket"] = set()
db: Optional[HypofuzzDatabase] = None


def _sample_reports(
    reports_by_worker: dict[str, list[ReportWithDiff]], *, soft_limit: int
) -> dict[str, list[ReportWithDiff]]:
    keep_start = 10
    keep_end = 10
    # Sample reports up to a soft limit of ``soft_limit`` reports.
    #
    # We keep the first and last 10 reports from each worker (which does not
    # count against ``soft_limit``), and fill in with ``soft_limit`` reports
    # sampled evenly across workers.
    #
    # An ideal algorithm would also:
    # * prefer keeping reports with new behaviors, which we expect to be less
    #   common than reports with new fingerprints.
    # * sample more tightly earlier on and less tightly later on. This improves
    #   log x axis graphs, which show more early intervals than late intervals.
    #   (but we probably don't want to do a full log sampling, which would make
    #   the linear graph look worse in comparison. Something inbetween log and
    #   linear).
    count_reports = sum(len(reports) for reports in reports_by_worker.values())
    by_worker = {}
    for worker_uuid, reports in reports_by_worker.items():
        if len(reports) <= keep_start + keep_end:
            by_worker[worker_uuid] = reports
            continue

        worker_step = (count_reports // soft_limit) + 1
        by_worker[worker_uuid] = (
            reports[:keep_start]
            + reports[keep_start:-keep_end:worker_step]
            + reports[-keep_end:]
        )
    return by_worker


class HypofuzzJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        data = json.dumps(
            convert_to_fuzzjson(content),
            ensure_ascii=False,
            separators=(",", ":"),
            cls=HypofuzzEncoder,
        )
        return data.encode("utf-8", errors="surrogatepass")


class HypofuzzWebsocket(abc.ABC):
    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket

    async def accept(self) -> None:
        await self.websocket.accept()

    async def receive_json(self) -> None:
        await self.websocket.receive_json()

    async def send_json(self, data: Any) -> None:
        await self.websocket.send_text(json.dumps(data, cls=HypofuzzEncoder))

    async def send_event(self, event: DashboardEventT) -> None:
        await self.send_json(event)

    @abc.abstractmethod
    async def initial(self, tests: dict[str, Test]) -> None:
        pass

    @abc.abstractmethod
    async def on_event(
        self, event_type: Literal["save", "delete"], key: DatabaseEventKey, value: Any
    ) -> None:
        pass


class OverviewWebsocket(HypofuzzWebsocket):
    async def initial(self, tests: dict[str, Test]) -> None:
        # we start by sending all tests, which is the most important
        # thing for the user to see first.
        event: AddTestsEvent = {
            "type": DashboardEventType.ADD_TESTS,
            "tests": [
                {
                    "database_key": test.database_key,
                    "nodeid": test.nodeid,
                    "failure": test.failure,
                }
                for test in tests.copy().values()
            ],
        }
        await self.send_event(event)

        # then we send the reports for each test.
        for test in tests.copy().values():
            # limit for performance
            reports_by_worker = _sample_reports(test.reports_by_worker, soft_limit=1000)
            for worker_uuid, reports in reports_by_worker.items():
                report_event: AddReportsEvent = {
                    "type": DashboardEventType.ADD_REPORTS,
                    "nodeid": test.nodeid,
                    "worker_uuid": worker_uuid,
                    "reports": [dashboard_report(report) for report in reports],
                }
                await self.send_event(report_event)

    async def on_event(
        self, event_type: Literal["save", "delete"], key: DatabaseEventKey, value: Any
    ) -> None:
        if event_type == "save":
            # don't send observations events, the overview page doesn't use
            # observations.
            event: DashboardEventT
            if key is DatabaseEventKey.REPORT:
                assert isinstance(value, Report)
                event = {
                    "type": DashboardEventType.ADD_REPORTS,
                    "nodeid": value.nodeid,
                    "worker_uuid": value.worker_uuid,
                    "reports": [dashboard_report(value)],
                }
                await self.send_event(event)
            if key is DatabaseEventKey.FAILURE:
                assert isinstance(value, Observation)
                event = {
                    "type": DashboardEventType.SET_FAILURE,
                    "nodeid": value.property,
                    "failure": dashboard_observation(value),
                }
                await self.send_event(event)

        if event_type == "delete":
            # TODO when we support multiple failures, we'll need to send the
            # specific observation that was deleted here, either via a
            # DELETE_OBSERVATION or a SET_FAILURES (note the plural)
            if key is DatabaseEventKey.FAILURE_OBSERVATION:
                event = {
                    "type": DashboardEventType.SET_FAILURE,
                    "nodeid": value.property,
                    "failure": None,
                }
                await self.send_event(event)


class TestWebsocket(HypofuzzWebsocket):
    def __init__(self, websocket: WebSocket, nodeid: str) -> None:
        super().__init__(websocket)
        self.nodeid = nodeid

    async def initial(self, tests: dict[str, Test]) -> None:
        if self.nodeid not in tests:
            return
        test = tests[self.nodeid]
        # send the test first
        test_data: AddTestsEvent = {
            "type": DashboardEventType.ADD_TESTS,
            "tests": [
                {
                    "database_key": test.database_key,
                    "nodeid": test.nodeid,
                    "failure": test.failure,
                }
            ],
        }
        await self.send_event(test_data)

        # then its reports. Note we don't currently downsample with _sample_reports
        # on individual test pages, unlike the overview page.
        for worker_uuid, reports in test.reports_by_worker.items():
            report_event: AddReportsEvent = {
                "type": DashboardEventType.ADD_REPORTS,
                "nodeid": test.nodeid,
                "worker_uuid": worker_uuid,
                "reports": [dashboard_report(report) for report in reports],
            }
            await self.send_event(report_event)

        # then its observations.
        for obs_type, observations in [
            ("rolling", test.rolling_observations),
            ("corpus", test.corpus_observations),
        ]:
            await self.send_event(
                {
                    "type": DashboardEventType.ADD_OBSERVATIONS,
                    "nodeid": self.nodeid,
                    "observation_type": obs_type,  # type: ignore
                    "observations": [
                        dashboard_observation(obs) for obs in observations
                    ],
                },
            )

    async def on_event(
        self, event_type: Literal["save", "delete"], key: DatabaseEventKey, value: Any
    ) -> None:
        if event_type == "save":
            event: DashboardEventT
            if key is DatabaseEventKey.REPORT:
                assert isinstance(value, Report)
                nodeid = value.nodeid
                event = {
                    "type": DashboardEventType.ADD_REPORTS,
                    "nodeid": nodeid,
                    "worker_uuid": value.worker_uuid,
                    "reports": [dashboard_report(value)],
                }
            elif key is DatabaseEventKey.FAILURE_OBSERVATION:
                assert isinstance(value, Observation)
                nodeid = value.property
                event = {
                    "type": DashboardEventType.SET_FAILURE,
                    "nodeid": nodeid,
                    "failure": dashboard_observation(value),
                }
            elif key in [
                DatabaseEventKey.ROLLING_OBSERVATION,
                DatabaseEventKey.CORPUS_OBSERVATION,
            ]:
                assert isinstance(value, Observation)
                nodeid = value.property
                event = {
                    "type": DashboardEventType.ADD_OBSERVATIONS,
                    "nodeid": nodeid,
                    "observation_type": (
                        "rolling"
                        if key is DatabaseEventKey.ROLLING_OBSERVATION
                        else "corpus"
                    ),
                    "observations": [dashboard_observation(value)],
                }
            else:
                # assert so I don't forget a case
                assert key in [
                    DatabaseEventKey.FAILURE_OBSERVATION,
                    DatabaseEventKey.CORPUS,
                ], key
                return

        if event_type == "delete":
            if key is DatabaseEventKey.FAILURE_OBSERVATION:
                nodeid = value.property
                event = {
                    "type": DashboardEventType.SET_FAILURE,
                    "nodeid": value.property,
                    "failure": None,
                }
            else:
                return

        # only broadcast event for this nodeid
        if nodeid != self.nodeid:
            return

        await self.send_event(event)


async def websocket(websocket: WebSocket) -> None:
    assert db is not None

    nodeid = websocket.query_params.get("nodeid")
    if nodeid is not None and nodeid not in TESTS:
        # requesting a test page that doesn't exist
        return

    websocket: HypofuzzWebsocket = (
        TestWebsocket(websocket, nodeid)
        if nodeid is not None
        else OverviewWebsocket(websocket)
    )
    await websocket.accept()
    websockets.add(websocket)

    await websocket.initial(TESTS)

    try:
        while True:
            await websocket.receive_json()
    except WebSocketDisconnect:
        websockets.remove(websocket)


async def broadcast_event(
    event_type: Literal["save", "delete"], key: DatabaseEventKey, value: Any
) -> None:
    # avoid error on websocket disconnecting during iteration
    for websocket in websockets.copy():
        await websocket.on_event(event_type, key, value)


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


def _patches() -> dict[str, str]:
    assert COLLECTION_RESULT is not None
    patches = make_and_save_patches(COLLECTION_RESULT.fuzz_targets, TESTS)
    return {name: str(patch_path.read_text()) for name, patch_path in patches.items()}


async def api_patches(request: Request) -> Response:
    return HypofuzzJSONResponse(_patches())


async def api_patch(request: Request) -> Response:
    patch_name = request.path_params["patch_name"]
    patches = _patches()
    if patch_name not in patches:
        return Response(status_code=404)
    return Response(content=patches[patch_name], media_type="text/x-patch")


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
            "rolling": test.rolling_observations,
            "corpus": test.corpus_observations,
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
    WebSocketRoute("/ws", websocket),
    Route("/api/tests/", api_tests),
    Route("/api/tests/{nodeid:path}", api_test),
    Route("/api/patches/", api_patches),
    Route("/api/patches/{patch_name}", api_patch),
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
            elif event.key is DatabaseEventKey.FAILURE_OBSERVATION:
                if event.value.property not in TESTS:
                    continue
                TESTS[event.value.property].failure = event.value
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
                TESTS[event.value.property].corpus_observations.append(event.value)

            await broadcast_event(event.type, event.key, event.value)

        # we're handling deletion events in a customish way, since event.value is
        # always None for databases which don't support value deletion. The value
        # we send to the websocket .on_event method is computed here and is specific
        # to each event type.
        if event.type == "delete":
            if event.key is DatabaseEventKey.FAILURE_OBSERVATION:
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
                        DatabaseEventKey.FAILURE_OBSERVATION,
                        previous_failure,
                    )


def get_failure_observations(database_key: bytes) -> dict[str, Observation]:
    assert db is not None

    failure_observations = {}
    for maybe_observed_choices in (
        *sorted(db.fetch_failures(database_key, shrunk=True), key=len),
        *sorted(db.fetch_failures(database_key, shrunk=False), key=len),
    ):
        if observation := db.fetch_failure_observation(
            database_key, maybe_observed_choices
        ):
            if observation.status is not ObservationStatus.FAILED:
                # This should never happen, but database corruption *can*.
                continue  # pragma: no cover
            # For failures, Hypothesis records the interesting_origin string
            # as the status_reason, which is how we dedupe errors upstream.
            if observation.status_reason not in failure_observations:
                failure_observations[observation.status_reason] = observation
    return failure_observations


def _load_initial_state(fuzz_target: FuzzProcess) -> None:
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


async def load_initial_state(fuzz_target: FuzzProcess) -> None:
    global LOADING_STATE

    await trio.to_thread.run_sync(_load_initial_state, fuzz_target)

    assert fuzz_target.nodeid in TESTS
    test = TESTS[fuzz_target.nodeid]
    LOADING_STATE[fuzz_target.database_key] = True

    for websocket in websockets.copy():
        # TODO: make this more granular? So we send incremental batches
        # of reports as they're loaded, etc. Would need trio.from_thread inside
        # _load_initial_state.
        await websocket.initial({test.nodeid: test})


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
    from hypofuzz.interface import _get_hypothesis_tests_with_pytest

    global COLLECTION_RESULT
    global db

    # we run a pytest collection step for the dashboard to pick up on the database
    # from any custom profiles, and as a ground truth for what tests to display.
    COLLECTION_RESULT = _get_hypothesis_tests_with_pytest(pytest_args)
    db = HypofuzzDatabase(settings().database)

    print(f"\n\tNow serving dashboard at  http://{host}:{port}/\n")
    trio.run(run_dashboard, port, host)
