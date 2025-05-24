"""Live web dashboard for a fuzzing run."""

import abc
import dataclasses
import itertools
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, TypeVar, Union

import black
import trio
from hypercorn.config import Config
from hypercorn.trio import serve
from hypothesis.database import (
    ListenerEventT,
)
from hypothesis.internal.cache import LRUCache
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.types import Scope
from starlette.websockets import WebSocket, WebSocketDisconnect
from trio import MemoryReceiveChannel

from hypofuzz.compat import bisect_right
from hypofuzz.database import (
    DatabaseEvent,
    DatabaseEventKey,
    HypofuzzEncoder,
    Observation,
    ObservationStatus,
    Phase,
    Report,
    ReportWithDiff,
    StatusCounts,
    get_db,
)
from hypofuzz.interface import CollectionResult
from hypofuzz.patching import make_and_save_patches

TESTS: dict[str, "Test"] = {}
COLLECTION_RESULT: Optional[CollectionResult] = None
websockets: set["HypofuzzWebsocket"] = set()

T = TypeVar("T")


@dataclass
class Test:
    database_key: str
    nodeid: str
    rolling_observations: list[Observation]
    corpus_observations: list[Observation]
    failure: Optional[Observation]
    reports_by_worker: dict[str, list[Report]]

    linear_reports: list[ReportWithDiff] = field(init=False)

    # prevent pytest from trying to collect this class as a test
    __test__ = False

    # TODO: turn into a regular class and add reports= and reports_by_workers
    # as alternative constructors? reports_by_workers is only to match the dashboard
    # class, we don't actually instantiate Test like that anywhere in python
    def __post_init__(self) -> None:
        self.linear_reports = []
        # map of since: float to (start_idx, list[StatusCounts])
        self._status_counts_cumsum: LRUCache[float, tuple[int, list[StatusCounts]]] = (
            LRUCache(16)
        )
        self._elapsed_time_cumsum: LRUCache[float, tuple[int, list[float]]] = LRUCache(
            16
        )

        reports_by_worker = self.reports_by_worker
        self.reports_by_worker = {}

        # TODO: use k-way merge for nlog(k)) performance, since reports_by_worker
        # is already sorted.
        # This sorting won't matter for correctness (once we correctly insert
        # out-of-order reports), but it will for performance, by minimizing the
        # number of .bisect calls in the worker reports list.
        for report in sorted(
            itertools.chain.from_iterable(reports_by_worker.values()),
            key=lambda r: r.elapsed_time,
        ):
            self.add_report(report)

        self._check_invariants()

    @staticmethod
    def _assert_reports_ordered(
        reports: list[ReportWithDiff], attributes: list[str]
    ) -> None:
        for attribute in attributes:
            assert all(
                getattr(r1, attribute) <= getattr(r2, attribute)
                for r1, r2 in zip(reports, reports[1:])
            ), (attribute, [getattr(r, attribute) for r in reports])

    def _check_invariants(self) -> None:
        # this entire function is pretty expensive, move from run-time to test-time
        # once we're more confident
        self._assert_reports_ordered(self.linear_reports, ["timestamp_monotonic"])

        linear_status_counts = self.linear_status_counts()
        assert all(
            v1 <= v2 for v1, v2 in zip(linear_status_counts, linear_status_counts[1:])
        ), linear_status_counts

        linear_elapsed_time = self.linear_elapsed_time()
        assert all(
            v1 <= v2 for v1, v2 in zip(linear_elapsed_time, linear_elapsed_time[1:])
        ), linear_elapsed_time
        assert (
            len(linear_elapsed_time)
            == len(linear_status_counts)
            == len(self.linear_reports)
        )

        for worker_uuid, reports in self.reports_by_worker.items():
            assert {r.nodeid for r in reports} == {self.nodeid}
            assert {r.database_key for r in reports} == {self.database_key}
            assert {r.worker_uuid for r in reports} == {worker_uuid}
            self._assert_reports_ordered(self.linear_reports, ["timestamp_monotonic"])

        # this is not always true due to floating point error accumulation.
        # total_elapsed_time = 0.0
        # for reports in self.reports_by_worker.values():
        #     total_elapsed_time += reports[-1].elapsed_time
        # assert self.elapsed_time == total_elapsed_time

    def add_report(self, report: Report) -> None:
        # we use last_report to compute timestamp_monotonic, and last_report_worker
        # to compute status_count_diff and elapsed_time_diff
        last_report = self.linear_reports[-1] if self.linear_reports else None
        last_worker_report = (
            None
            if report.worker_uuid not in self.reports_by_worker
            else self.reports_by_worker[report.worker_uuid][-1]
        )
        if (
            last_worker_report is not None
            and last_worker_report.elapsed_time > report.elapsed_time
        ):
            # If last_report.elapsed_time > report.elapsed_time, the reports have arrived
            # out of order. we've already accounted for the diff of `report`; last_report
            # essentially became the combined report of report + last_report.
            #
            # TODO instead of dropping this report, insert it into the lists at
            # the appropriate index, and recompute the diff for the next
            # report. That way the e.g. dashboard graph still gets the report.
            return

        linear_report = ReportWithDiff.from_reports(
            report, last_report=last_report, last_worker_report=last_worker_report
        )
        # support the by-worker access pattern. We only access index [-1] though
        # - should we store self.last_reports_by_worker instead?
        self.reports_by_worker.setdefault(report.worker_uuid, []).append(linear_report)
        # Phase.REPLAY does not count towards:
        #   * status_counts
        #   * elapsed_time
        #   * reports
        #   * behaviors
        #   * fingerprints
        #   * phase (should we change this? would cause status flipflop with multiple workers)
        # nor is it displayed on dashboard graphs.
        # This is fine for display purposes, since these statistics are intended
        # to convey the time spent searching for bugs. But we should be careful
        # when measuring cost to compute a separate "overhead" statistic which
        # takes every input and elapsed_time into account regardless of phase.
        if linear_report.phase is not Phase.REPLAY:
            self.linear_reports.append(linear_report)

    @property
    def phase(self) -> Optional[Phase]:
        return self.linear_reports[-1].phase if self.linear_reports else None

    @property
    def behaviors(self) -> int:
        return self.linear_reports[-1].behaviors if self.linear_reports else 0

    @property
    def fingerprints(self) -> int:
        return self.linear_reports[-1].fingerprints if self.linear_reports else 0

    def ninputs(self, since: float = -math.inf) -> int:
        return sum(self.linear_status_counts(since=since)[-1].values())

    def _cumsum(
        self,
        *,
        cache: LRUCache,
        attr: str,
        since: float = -math.inf,
        initial: T,
    ) -> list[T]:
        cumsum: list[T]
        if since in cache:
            (start_idx, cumsum) = cache[since]
            if len(cumsum) < len(self.linear_reports[start_idx:]):
                # extend cumsum with any new reports
                running = cumsum[-1] if cumsum else initial
                for report in self.linear_reports[start_idx + len(cumsum) :]:
                    value = getattr(report, attr)
                    assert value >= initial
                    running += value
                    cumsum.append(running)
                cache[since] = (start_idx, cumsum)

            return cumsum

        cumsum = []
        start_idx = bisect_right(
            self.linear_reports, since, key=lambda r: r.timestamp_monotonic
        )
        running = initial
        for report in self.linear_reports[start_idx:]:
            value = getattr(report, attr)
            assert value >= initial
            running += value
            cumsum.append(running)
        cache[since] = (start_idx, cumsum)
        return cumsum

    def linear_status_counts(self, *, since: float = -math.inf) -> list[StatusCounts]:
        return self._cumsum(
            cache=self._status_counts_cumsum,
            attr="status_counts_diff",
            since=since,
            initial=StatusCounts(),
        )

    def linear_elapsed_time(self, *, since: float = -math.inf) -> list[float]:
        return self._cumsum(
            cache=self._elapsed_time_cumsum,
            attr="elapsed_time_diff",
            since=since,
            initial=0.0,
        )


def test_for_websocket(test: Test) -> dict[str, Any]:
    # only send necessary attributes for the dashboard
    test = dataclasses.asdict(test)
    # report.worker is duplicated among all reports in a reports_by_worker list.
    # drop them and add them as an attribute to reports_by_workers?
    # so reports_by_workers: dict[str, tuple[WorkerIdentity, list[Report]]]
    del test["rolling_observations"]
    del test["corpus_observations"]
    del test["linear_reports"]
    test["reports_by_worker"] = {
        worker_uuid: [report_for_websocket(report) for report in reports]
        for worker_uuid, reports in test["reports_by_worker"].items()
    }
    return test


def report_for_websocket(report: Union[Report, dict[str, Any]]) -> dict[str, Any]:
    report = report.copy() if isinstance(report, dict) else dataclasses.asdict(report)
    # we send reports to the dashboard in two contexts: attached to a node and worker,
    # and as a standalone report. In the former, the dashboard already knows
    # the nodeid and worker uuid, and deleting them avoids substantial overhead.
    # In the latter, we send the necessary attributes separately.
    del report["worker_uuid"]
    del report["database_key"]
    del report["nodeid"]
    return report


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
    async def on_event(self, header: dict[str, Any], data: Any) -> None:
        pass


class OverviewWebsocket(HypofuzzWebsocket):
    async def initial(self, tests: dict[str, Test]) -> None:
        tests = {nodeid: test_for_websocket(test) for nodeid, test in tests.items()}
        await self.send_event({"type": "initial", "initial_type": "tests"}, tests)
        # don't send observations event, overview page doesn't use them

    async def on_event(self, header: dict[str, Any], data: Any) -> None:
        if header["type"] == "save":
            if header["key"] not in [
                DatabaseEventKey.REPORT,
                DatabaseEventKey.FAILURE,
            ]:
                return
            if header["key"] is DatabaseEventKey.REPORT:
                assert isinstance(data, Report)
                data = {
                    "nodeid": data.nodeid,
                    "worker_uuid": data.worker_uuid,
                    "report": report_for_websocket(data),
                }
            await self.send_event(header, data)


class TestWebsocket(HypofuzzWebsocket):
    def __init__(self, websocket: WebSocket, nodeid: str) -> None:
        super().__init__(websocket)
        self.nodeid = nodeid

    async def initial(self, tests: dict[str, Test]) -> None:
        test = tests[self.nodeid]
        # split initial event in two pieces: test (without observations), and observations.
        tests = {self.nodeid: test_for_websocket(test)}
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
            if header["key"] is DatabaseEventKey.REPORT:
                assert isinstance(data, Report)
                nodeid = data.nodeid
                data = {
                    "nodeid": nodeid,
                    "worker_uuid": data.worker_uuid,
                    "report": report_for_websocket(data),
                }
            elif header["key"] in [
                DatabaseEventKey.FAILURE,
                DatabaseEventKey.ROLLING_OBSERVATION,
                DatabaseEventKey.CORPUS_OBSERVATION,
            ]:
                assert isinstance(data, Observation)
                nodeid = data.property
            elif header["key"] in [
                DatabaseEventKey.FAILURE_OBSERVATION,
                DatabaseEventKey.CORPUS,
            ]:
                return
            else:
                raise NotImplementedError(f"unhandled event {header}")

            # only broadcast event for this nodeid
            if nodeid != self.nodeid:
                return

            await self.send_event(header, data)


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

        await broadcast_event({"type": event.type, "key": event.key}, event.value)


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
            for choices in db.fetch_corpus(key)
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
            reports_by_worker=reports_by_worker,
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
