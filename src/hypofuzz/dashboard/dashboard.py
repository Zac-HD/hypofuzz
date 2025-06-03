"""Live web dashboard for a fuzzing run."""

import abc
import json
import math
from collections import defaultdict
from enum import IntEnum
from pathlib import Path
from typing import Any, Literal, Optional

import black
import trio
from hypercorn.config import Config
from hypercorn.trio import serve
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

from hypofuzz.dashboard.patching import make_and_save_patches
from hypofuzz.dashboard.test import Test
from hypofuzz.database import (
    DatabaseEvent,
    DatabaseEventKey,
    HypofuzzEncoder,
    Observation,
    ObservationStatus,
    Report,
    get_db,
)
from hypofuzz.interface import CollectionResult

TESTS: dict[str, "Test"] = {}
COLLECTION_RESULT: Optional[CollectionResult] = None
websockets: set["HypofuzzWebsocket"] = set()


class DashboardEventType(IntEnum):
    # minimize header frame overhead with a shared IntEnum definition between
    # python and ts.
    ADD_TESTS = 1
    ADD_REPORTS = 2
    ADD_ROLLING_OBSERVATIONS = 3
    ADD_CORPUS_OBSERVATIONS = 4
    SET_FAILURE = 5


def test_for_websocket(test: Test) -> dict[str, Any]:
    # Limit to 1000 reports per test. If we're over 1000 total reports, sample
    # evenly from each worker.
    #
    # As a temporary stopgap until a more intelligent algorithm, sample the
    # entirety of the first 20 reports per worker, then `::step` after. This
    # helps with (4).
    #
    # A more intelligent algorithm would:
    # (1) sample evenly from the aggregate reports list (instead of per-worker)
    # (2) prefer keeping reports with new behaviors which we expect to be less
    #     common than reports with new fingerprints.
    # (3) always keep the last report, so the graph (and aggregate stats) is as up
    #     to date as possible
    # (4) sample more tightly earlier on and less tightly later on, since there is
    #     more behavior and fingerprint growth early. This is especially important
    #     for log x axis graphs, which show more early intervals than late intervals
    step = (len(test.linear_reports) // 1000) + 1
    return {
        "database_key": test.database_key,
        "nodeid": test.nodeid,
        "failure": test.failure,
        "reports_by_worker": {
            worker_uuid: [
                report_for_websocket(report)
                for report in reports[:20] + reports[20::step]
            ]
            for worker_uuid, reports in test.reports_by_worker.items()
        },
    }


def report_for_websocket(report: Report) -> dict[str, Any]:
    # we send reports to the dashboard in two contexts: attached to a node and worker,
    # and as a standalone report. In the former, the dashboard already knows
    # the nodeid and worker uuid, and deleting them avoids substantial overhead.
    # In the latter, we send the necessary attributes separately.
    return {
        "elapsed_time": report.elapsed_time,
        "status_counts": report.status_counts,
        "behaviors": report.behaviors,
        "fingerprints": report.fingerprints,
        "timestamp": report.timestamp,
        "since_new_branch": report.since_new_branch,
        "phase": report.phase,
    }


class HypofuzzJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            separators=(",", ":"),
            cls=HypofuzzEncoder,
        ).encode("utf-8", errors="surrogatepass")


class HypofuzzWebsocket(abc.ABC):
    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket

    async def accept(self) -> None:
        await self.websocket.accept()

    async def receive_json(self) -> None:
        await self.websocket.receive_json()

    async def send_json(self, data: Any) -> None:
        await self.websocket.send_text(json.dumps(data, cls=HypofuzzEncoder))

    async def send_event(self, header: dict[str, Any], data: Any) -> None:
        await self.websocket.send_text(
            f"{json.dumps(header, cls=HypofuzzEncoder)}|{json.dumps(data, cls=HypofuzzEncoder)}"
        )

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
        # should we be passing in some global nursery here instead? I think this
        # will block any callers until all send_event tasks complete, right?
        # which we don't necessarily care about (though it's less important than
        # sending all the events here in parallel).
        async with trio.open_nursery() as nursery:
            # we start by sending all tests, which is the most important
            # thing for the user to see first.
            tests_data = {
                "tests": [
                    {
                        "database_key": test.database_key,
                        "nodeid": test.nodeid,
                        "failure": test.failure,
                    }
                    for test in tests.values()
                ]
            }
            nursery.start_soon(
                self.send_event,
                {"type": DashboardEventType.ADD_TESTS},
                tests_data,
            )

            # Then we send the reports for each test.
            for test in tests.values():
                for worker_uuid, reports in test.reports_by_worker.items():
                    report_data = {
                        "nodeid": test.nodeid,
                        "worker_uuid": worker_uuid,
                        "reports": [report_for_websocket(report) for report in reports],
                    }
                    nursery.start_soon(
                        self.send_event,
                        {"type": DashboardEventType.ADD_REPORTS},
                        report_data,
                    )

    async def on_event(
        self, event_type: Literal["save", "delete"], key: DatabaseEventKey, value: Any
    ) -> None:
        if event_type == "save":
            # don't send observations events, the overview page doesn't use
            # observations.
            if key is DatabaseEventKey.REPORT:
                assert isinstance(value, Report)
                data: Any = {
                    "nodeid": value.nodeid,
                    "worker_uuid": value.worker_uuid,
                    "reports": [report_for_websocket(value)],
                }
                await self.send_event({"type": DashboardEventType.ADD_REPORTS}, data)
            if key is DatabaseEventKey.FAILURE:
                assert isinstance(value, Observation)
                data = {
                    "nodeid": value.property,
                    "failure": value,
                }
                await self.send_event({"type": DashboardEventType.SET_FAILURE}, data)


class TestWebsocket(HypofuzzWebsocket):
    def __init__(self, websocket: WebSocket, nodeid: str) -> None:
        super().__init__(websocket)
        self.nodeid = nodeid

    async def initial(self, tests: dict[str, Test]) -> None:
        test = tests[self.nodeid]
        async with trio.open_nursery() as nursery:
            # send the test first
            test_data = {
                "database_key": test.database_key,
                "nodeid": test.nodeid,
                "failure": test.failure,
            }
            nursery.start_soon(
                self.send_event,
                {"type": DashboardEventType.ADD_TESTS},
                [test_data],
            )

            # then its reports
            for worker_uuid, reports in test.reports_by_worker.items():
                report_data = {
                    "nodeid": test.nodeid,
                    "worker_uuid": worker_uuid,
                    "reports": [report_for_websocket(report) for report in reports],
                }
                nursery.start_soon(
                    self.send_event,
                    {"type": DashboardEventType.ADD_REPORTS},
                    report_data,
                )

            nursery.start_soon(
                self.send_event,
                {"type": DashboardEventType.ADD_ROLLING_OBSERVATIONS},
                {"nodeid": self.nodeid, "observations": test.rolling_observations},
            )
            nursery.start_soon(
                self.send_event,
                {"type": DashboardEventType.ADD_CORPUS_OBSERVATIONS},
                {"nodeid": self.nodeid, "observations": test.corpus_observations},
            )

    async def on_event(
        self, event_type: Literal["save", "delete"], key: DatabaseEventKey, value: Any
    ) -> None:
        if event_type == "save":
            if key is DatabaseEventKey.REPORT:
                assert isinstance(value, Report)
                nodeid = value.nodeid
                value = {
                    "nodeid": nodeid,
                    "worker_uuid": value.worker_uuid,
                    "reports": [report_for_websocket(value)],
                }
                dashboard_event = DashboardEventType.ADD_REPORTS
            elif key is DatabaseEventKey.FAILURE:
                assert isinstance(value, Observation)
                nodeid = value.property
                dashboard_event = DashboardEventType.SET_FAILURE
                value = {
                    "nodeid": nodeid,
                    "failure": value,
                }
            elif key in [
                DatabaseEventKey.ROLLING_OBSERVATION,
                DatabaseEventKey.CORPUS_OBSERVATION,
            ]:
                assert isinstance(value, Observation)
                nodeid = value.property
                dashboard_event = {
                    DatabaseEventKey.ROLLING_OBSERVATION: DashboardEventType.ADD_ROLLING_OBSERVATIONS,
                    DatabaseEventKey.CORPUS_OBSERVATION: DashboardEventType.ADD_CORPUS_OBSERVATIONS,
                }[key]
                value = {
                    "nodeid": nodeid,
                    "observations": [value],
                }
            else:
                # assert so I don't forget a case
                assert key in [
                    DatabaseEventKey.FAILURE_OBSERVATION,
                    DatabaseEventKey.CORPUS,
                ], key
                return

            # only broadcast event for this nodeid
            if nodeid != self.nodeid:
                return

            await self.send_event({"type": dashboard_event}, value)


async def websocket(websocket: WebSocket) -> None:
    assert COLLECTION_RESULT is not None
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
    # avoid websocket disconnecting during iteration and causing a RuntimeError
    for websocket in websockets.copy():
        await websocket.on_event(event_type, key, value)


def try_format(code: str) -> str:
    try:
        return black.format_str(code, mode=black.FileMode())
    except Exception:
        return code


async def api_tests(request: Request) -> Response:
    return HypofuzzJSONResponse(TESTS)


async def api_test(request: Request) -> Response:
    nodeid = request.path_params["nodeid"]
    return HypofuzzJSONResponse(TESTS[nodeid])


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
    tests = {nodeid: test_for_websocket(test) for nodeid, test in TESTS.items()}
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

        if event.type == "delete":
            # don't send deletion events to the dashboard, for now
            continue

        assert event.type == "save"
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
            TESTS[event.value.property].rolling_observations.append(event.value)
        elif event.key is DatabaseEventKey.CORPUS_OBSERVATION:
            if event.value.property not in TESTS:
                continue
            TESTS[event.value.property].corpus_observations.append(event.value)

        await broadcast_event(event.type, event.key, event.value)


async def run_dashboard(port: int, host: str) -> None:
    assert COLLECTION_RESULT is not None

    send_channel, receive_channel = trio.open_memory_channel[ListenerEventT](math.inf)
    token = trio.lowlevel.current_trio_token()

    def send_nowait_from_anywhere(msg: ListenerEventT) -> None:
        # DirectoryBasedExampleDatabase sends events from a background thread (via watchdog),
        # so we need to support sending from anywhere, i.e. whether or not the calling thread
        # has any Trio state.  We can do that with the following branch:
        try:
            trio.lowlevel.current_task()
        except RuntimeError:
            trio.from_thread.run_sync(send_channel.send_nowait, msg, trio_token=token)
        else:
            send_channel.send_nowait(msg)

    db = get_db()
    # load initial database state before starting dashboard
    for fuzz_target in COLLECTION_RESULT.fuzz_targets:
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
            observation
            for observation in corpus_observations
            if observation is not None
        ]

        failure_observations = {}
        for maybe_observed in (
            *sorted(db.fetch_failures(key, shrunk=True), key=len),
            *sorted(db.fetch_failures(key, shrunk=False), key=len),
        ):
            if failure := db.fetch_failure_observation(key, maybe_observed):
                if failure.status is not ObservationStatus.FAILED:
                    # This should never happen, but database corruption *can*.
                    continue  # pragma: no cover
                # For failures, Hypothesis records the interesting_origin string
                # as the status_reason, which is how we dedupe errors upstream.
                if failure.status_reason not in failure_observations:
                    failure_observations[failure.status_reason] = failure

        reports_by_worker = defaultdict(list)
        for report in sorted(db.fetch_reports(key), key=lambda r: r.elapsed_time):
            reports_by_worker[report.worker_uuid].append(report)

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

    # Any database events that get submitted while we're computing initial state
    # won't be displayed until a dashboard restart. We could solve this by adding the
    # listener first, then storing reports in a queue, to be resolved after
    # computing initial state.
    #
    # For now this is an acceptable loss.
    db._db.add_listener(send_nowait_from_anywhere)
    async with trio.open_nursery() as nursery:
        nursery.start_soon(serve_app, app, host, port)  # type: ignore
        nursery.start_soon(handle_event, receive_channel)


def start_dashboard_process(
    port: int, *, pytest_args: list, host: str = "localhost"
) -> None:
    from hypofuzz.interface import _get_hypothesis_tests_with_pytest

    global COLLECTION_RESULT
    # we run a pytest collection step for the dashboard to pick up on the database
    # from any custom profiles, and as a ground truth for what tests to display.
    COLLECTION_RESULT = _get_hypothesis_tests_with_pytest(pytest_args)

    print(f"\n\tNow serving dashboard at  http://{host}:{port}/\n")
    trio.run(run_dashboard, port, host)
