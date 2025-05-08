"""Live web dashboard for a fuzzing run."""

import abc
import dataclasses
import json
import math
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, Optional

import black
import trio
from hypercorn.config import Config
from hypercorn.trio import serve
from hypothesis import settings
from hypothesis.database import (
    BackgroundWriteDatabase,
    ListenerEventT,
)
from hypothesis.internal.conjecture.data import Status
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect
from trio import MemoryReceiveChannel

from hypofuzz.database import (
    HypofuzzDatabase,
    HypofuzzEncoder,
    Observation,
    Phase,
    Report,
    ReportOffsets,
    StatusCounts,
    is_corpus_observation_key,
    is_failure_observation_key,
    is_observation_key,
    linearize_reports,
    reports_key,
)
from hypofuzz.interface import CollectionResult
from hypofuzz.patching import make_and_save_patches

TESTS: dict[str, "Test"] = {}
COLLECTION_RESULT: Optional[CollectionResult] = None
websockets: set["HypofuzzWebsocket"] = set()


@dataclass
class Test:
    database_key: str
    nodeid: str
    # we assume these reports have been linearized with linearize_reports.
    reports: list[Report]
    reports_offsets: ReportOffsets
    rolling_observations: list[Observation]
    corpus_observations: list[Observation]
    failure: Optional[Observation]
    status_counts: StatusCounts = field(init=False)
    elapsed_time: float = field(init=False)

    # prevent pytest from trying to collect this class as a test
    __test__ = False

    def __post_init__(self) -> None:
        self.status_counts = sum(
            self.reports_offsets.status_counts.values(),
            start=StatusCounts(dict.fromkeys(Status, 0)),
        )
        self.elapsed_time = sum(self.reports_offsets.elapsed_time.values())
        self._check_invariants()

    def _check_invariants(self) -> None:
        # elapsed_time and status_counts should be monotonically
        # increasing. Note that timestamp may not be, if reports get added to the
        # test by add_report out of order. linearize_reports does guarantee
        # monotonicity of timestamp, though.
        for attribute in ["elapsed_time", "status_counts"]:
            assert all(
                getattr(r1, attribute) <= getattr(r2, attribute)
                for r1, r2 in zip(self.reports, self.reports[1:])
            ), (attribute, [getattr(r, attribute) for r in self.reports])

        # we tracak a separate attibute for the total count for efficiency, but
        # they should be equal.
        assert self.status_counts == sum(
            self.reports_offsets.status_counts.values(),
            start=StatusCounts(dict.fromkeys(Status, 0)),
        )
        # this is not always true due to floating point error accumulation.
        # assert self.elapsed_time == sum(self.reports_offsets.elapsed_time.values())

    def add_report(self, report: Report) -> None:
        status_counts = self.reports_offsets.status_counts
        elapsed_time = self.reports_offsets.elapsed_time
        counts_diff = report.status_counts - status_counts.setdefault(
            report.worker.uuid, StatusCounts(dict.fromkeys(Status, 0))
        )
        elapsed_diff = report.elapsed_time - elapsed_time.setdefault(
            report.worker.uuid, 0.0
        )
        assert all(count >= 0 for count in counts_diff.values())
        assert elapsed_diff >= 0.0
        report = dataclasses.replace(
            report,
            status_counts=self.status_counts + counts_diff,
            elapsed_time=self.elapsed_time + elapsed_diff,
        )
        # we count status counts and elapsed_time from Phase.REPLAY - it's still
        # cpu time being used, after all. But we do not add reports for Phase.REPLAY,
        # because it's not progress being made.
        self.status_counts += counts_diff
        self.elapsed_time += elapsed_diff
        status_counts[report.worker.uuid] += counts_diff
        elapsed_time[report.worker.uuid] += elapsed_diff
        if report.phase is not Phase.REPLAY:
            self.reports.append(report)

        self._check_invariants()

    def phase(self) -> Optional[Phase]:
        if not self.reports:
            return None
        return self.reports[-1].phase


class HypofuzzJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        # arguments copied from starlette.JSONResponse, with the addition of
        # cls=HypofuzzEncoder
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
            f"{json.dumps(header)}|{json.dumps(data, cls=HypofuzzEncoder)}"
        )

    @abc.abstractmethod
    async def initial(self, tests: dict[str, Test]) -> None:
        pass

    @abc.abstractmethod
    async def on_event(self, header: dict[str, Any], data: Any) -> None:
        pass


class OverviewWebsocket(HypofuzzWebsocket):
    async def initial(self, tests: dict[str, Test]) -> None:
        tests = {
            nodeid: dataclasses.replace(
                test, rolling_observations=[], corpus_observations=[]
            )
            for nodeid, test in tests.items()
        }
        await self.send_event({"type": "initial", "initial_type": "tests"}, tests)
        # don't send observations event, overview page doesn't use them

    async def on_event(self, header: dict[str, Any], data: Any) -> None:
        if header["type"] == "save":
            if header["save_type"] in ["rolling_observation", "corpus_observation"]:
                return
            await self.send_event(header, data)


class TestWebsocket(HypofuzzWebsocket):
    def __init__(self, websocket: WebSocket, nodeid: str) -> None:
        super().__init__(websocket)
        self.nodeid = nodeid

    async def initial(self, tests: dict[str, Test]) -> None:
        test = tests[self.nodeid]
        # split initial event in two pieces: test (without observations), and observations.
        tests = {
            self.nodeid: dataclasses.replace(
                test, rolling_observations=[], corpus_observations=[]
            )
        }
        observations = {
            self.nodeid: {
                "rolling": test.rolling_observations,
                "corpus": test.corpus_observations,
            }
        }
        await self.send_event({"type": "initial", "initial_type": "tests"}, tests)
        await self.send_event(
            {"type": "initial", "initial_type": "observations"}, observations
        )

    async def on_event(self, header: dict[str, Any], data: Any) -> None:
        if header["type"] == "save":
            if header["save_type"] == "report":
                assert isinstance(data, Report)
                nodeid = data.nodeid
            elif header["save_type"] in [
                "failure",
                "rolling_observation",
                "corpus_observation",
            ]:
                assert isinstance(data, Observation)
                nodeid = data.property
            else:
                raise AssertionError

            # only broadcast event for this nodeid
            if nodeid != self.nodeid:
                return

            await self.send_event(header, data)


async def websocket(websocket: WebSocket) -> None:
    assert COLLECTION_RESULT is not None

    websocket: HypofuzzWebsocket = (
        TestWebsocket(websocket, nodeid)
        if (nodeid := websocket.query_params.get("nodeid"))
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


async def broadcast_event(header: dict[str, Any], data: Any) -> None:
    # avoid websocket disconnecting during iteration and causing a RuntimeError
    for websocket in websockets.copy():
        await websocket.on_event(header, data)


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
    tests = {
        nodeid: dataclasses.replace(
            test, rolling_observations=[], corpus_observations=[]
        )
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


dist = Path(__file__).parent / "frontend" / "dist"
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
    # catchall fallback. react will handle the routing of dynamic urls here,
    # such as to a node id.
    Route("/{path:path}", FileResponse(dist / "index.html")),
]
app = Starlette(routes=routes)


async def serve_app(app: Any, host: str, port: str) -> None:
    config = Config()
    config.bind = [f"{host}:{port}"]
    await serve(app, config)


async def handle_event(receive_channel: MemoryReceiveChannel) -> None:
    async for event_type, args in receive_channel:
        if event_type == "save":
            key, value = args
            assert value is not None
            if key.endswith(reports_key):
                report = Report.from_json(json.loads(value))
                # this is an in-process transmission, it should never be out of
                # date with the Report schema
                assert report is not None
                TESTS[report.nodeid].add_report(report)
                await broadcast_event({"type": "save", "save_type": "report"}, report)
            elif is_failure_observation_key(key):
                observation = Observation.from_json(json.loads(value))
                assert observation is not None
                TESTS[observation.property].failure = observation
                await broadcast_event(
                    {"type": "save", "save_type": "failure"}, observation
                )
            elif is_observation_key(key):
                observation = Observation.from_json(json.loads(value))
                assert observation is not None
                TESTS[observation.property].rolling_observations.append(observation)
                await broadcast_event(
                    {"type": "save", "save_type": "rolling_observation"}, observation
                )
            elif is_corpus_observation_key(key):
                observation = Observation.from_json(json.loads(value))
                assert observation is not None
                TESTS[observation.property].corpus_observations.append(observation)
                await broadcast_event(
                    {"type": "save", "save_type": "corpus_observation"}, observation
                )

        # we'll want to send the relinearized history to the dashboard every now
        # and then (via a "refresh" event), to avoid falling too far out of sync.
        # Unclear whether we want this on a long debounce for any arbitrary event,
        # or on a timer.


# cache to make the db a singleton. We defer creation until first-usage to ensure
# that we use the test-time database setting, rather than init-time.
# TODO we want to use BackgroundWriteDatabase in workers to, not just dashboard
@cache
def get_db() -> HypofuzzDatabase:
    db = settings().database
    if isinstance(db, BackgroundWriteDatabase):
        return HypofuzzDatabase(db)
    return HypofuzzDatabase(BackgroundWriteDatabase(db))


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
        key = fuzz_target.database_key
        reports = linearize_reports(list(db.fetch_reports(key)))
        assert all(fuzz_target.nodeid == report.nodeid for report in reports.reports)

        rolling_observations = list(db.fetch_observations(key))
        corpus_observations = [
            db.fetch_corpus_observation(key, choices)
            for choices in db.fetch_corpus(key)
        ]
        corpus_observations = [
            observation
            for observation in corpus_observations
            if observation is not None
        ]
        failure = None
        if failures := (
            list(db.fetch_failures(key, shrunk=True))
            + list(db.fetch_failures(key, shrunk=False))
        ):
            # if there are multiple failures, pick the first one
            failure = db.fetch_failure_observation(key, failures[0])

        TESTS[fuzz_target.nodeid] = Test(
            database_key=fuzz_target.database_key_str,
            nodeid=fuzz_target.nodeid,
            reports=reports.reports,
            reports_offsets=reports.offsets,
            rolling_observations=rolling_observations,
            corpus_observations=corpus_observations,
            failure=failure,
        )

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
