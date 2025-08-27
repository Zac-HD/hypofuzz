import abc
import dataclasses
import json
from typing import Any

from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from hypofuzz.dashboard.models import (
    AddObservationsEvent,
    AddReportsEvent,
    AddTestsEvent,
    DashboardEventT,
    DashboardEventType,
    SetStatusEvent,
    TestLoadFinishedEvent,
    dashboard_failures,
    dashboard_fatal_failure,
    dashboard_observation,
    dashboard_report,
)
from hypofuzz.dashboard.test import Test
from hypofuzz.database import HypofuzzEncoder, ReportWithDiff

websockets: set["HypofuzzWebsocket"] = set()


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
        data = {
            "type": event.type.value,
            **{
                field.name: getattr(event, field.name)
                for field in dataclasses.fields(event)
            },
        }
        await self.send_json(data)

    async def on_connect(self) -> None:
        pass

    async def send_tests(self, tests: dict[str, Test]) -> None:
        pass

    async def on_event(self, event: DashboardEventT) -> None:
        pass


class OverviewWebsocket(HypofuzzWebsocket):
    async def send_tests(self, tests: dict[str, Test]) -> None:
        from hypofuzz.dashboard.dashboard import COLLECTION_RESULT, TESTS

        assert COLLECTION_RESULT is not None

        event = SetStatusEvent(
            count_tests=len(COLLECTION_RESULT.fuzz_targets),
            count_tests_loaded=len(TESTS),
        )
        await self.send_event(event)

        # we start by sending all tests, which is the most important
        # thing for the user to see first.
        event = AddTestsEvent(
            tests=[
                {
                    "database_key": test.database_key,
                    "nodeid": test.nodeid,
                    "failures": dashboard_failures(test.failures),
                    "fatal_failure": (
                        None
                        if test.fatal_failure is None
                        else dashboard_fatal_failure(test.fatal_failure)
                    ),
                    "stability": test.stability,
                }
                for test in tests.copy().values()
            ],
        )
        await self.send_event(event)

        # then we send the reports for each test.
        for test in tests.copy().values():
            # limit for performance
            reports_by_worker = _sample_reports(test.reports_by_worker, soft_limit=1000)
            for worker_uuid, reports in reports_by_worker.items():
                report_event = AddReportsEvent(
                    nodeid=test.nodeid,
                    worker_uuid=worker_uuid,
                    reports=[dashboard_report(report) for report in reports],
                )
                await self.send_event(report_event)

            await broadcast_event(TestLoadFinishedEvent(nodeid=test.nodeid))

    async def on_event(self, event: DashboardEventT) -> None:
        # skip observations to the websocket page
        if event.type in [DashboardEventType.ADD_OBSERVATIONS]:
            return
        await self.send_event(event)


class TestWebsocket(HypofuzzWebsocket):
    def __init__(self, websocket: WebSocket, nodeid: str) -> None:
        super().__init__(websocket)
        self.nodeid = nodeid

    async def send_tests(self, tests: dict[str, Test]) -> None:
        if self.nodeid not in tests:
            return
        test = tests[self.nodeid]
        # send the test first
        test_data = AddTestsEvent(
            tests=[
                {
                    "database_key": test.database_key,
                    "nodeid": test.nodeid,
                    "failures": dashboard_failures(test.failures),
                    "fatal_failure": (
                        None
                        if test.fatal_failure is None
                        else dashboard_fatal_failure(test.fatal_failure)
                    ),
                    "stability": test.stability,
                }
            ],
        )
        await self.send_event(test_data)

        # then its reports. Note we still downsample reports_by_worker, but with
        # a higher limit than the overview page.
        reports_by_worker = _sample_reports(test.reports_by_worker, soft_limit=5_000)
        for worker_uuid, reports in reports_by_worker.items():
            report_event = AddReportsEvent(
                nodeid=test.nodeid,
                worker_uuid=worker_uuid,
                reports=[dashboard_report(report) for report in reports],
            )
            await self.send_event(report_event)

        # then its observations.
        for obs_type, observations in [
            ("rolling", test.rolling_observations),
            ("corpus", test.corpus_observations),
        ]:
            await self.send_event(
                AddObservationsEvent(
                    nodeid=self.nodeid,
                    observation_type=obs_type,  # type: ignore
                    observations=[dashboard_observation(obs) for obs in observations],
                )
            )

        await broadcast_event(TestLoadFinishedEvent(nodeid=self.nodeid))

    async def on_event(self, event: DashboardEventT) -> None:
        # we only send these events for test websockets
        if event.type not in [
            DashboardEventType.ADD_REPORTS,
            DashboardEventType.ADD_OBSERVATIONS,
            DashboardEventType.ADD_FAILURES,
            DashboardEventType.SET_FAILURES,
            DashboardEventType.TEST_LOAD_FINISHED,
        ]:
            return

        assert hasattr(event, "nodeid")
        # only broadcast event for this nodeid
        if event.nodeid != self.nodeid:
            return

        await self.send_event(event)


async def broadcast_event(event: DashboardEventT) -> None:
    # avoid error on websocket disconnecting during iteration
    for websocket in websockets.copy():
        await websocket.on_event(event)


async def websocket_route(websocket: WebSocket) -> None:
    from hypofuzz.dashboard.dashboard import TESTS, db

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

    await websocket.on_connect()
    await websocket.send_tests(TESTS)

    try:
        while True:
            await websocket.receive_json()
    except WebSocketDisconnect:
        websockets.remove(websocket)


websocket_routes = [WebSocketRoute("/ws", websocket_route)]
