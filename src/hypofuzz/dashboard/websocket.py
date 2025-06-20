import abc
import json
from typing import Any, Literal

from starlette.websockets import WebSocket, WebSocketDisconnect

from hypofuzz.dashboard.models import (
    AddReportsEvent,
    AddTestsEvent,
    DashboardEventT,
    DashboardEventType,
    SetStatusEvent,
    dashboard_observation,
    dashboard_report,
)
from hypofuzz.dashboard.test import Test
from hypofuzz.database import (
    DatabaseEventKey,
    HypofuzzEncoder,
    Observation,
    Report,
    ReportWithDiff,
)

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
        await self.send_json(event)

    async def on_connect(self) -> None:
        pass

    async def send_tests(self, tests: dict[str, Test]) -> None:
        pass

    async def on_event(
        self, event_type: Literal["save", "delete"], key: DatabaseEventKey, value: Any
    ) -> None:
        pass


class OverviewWebsocket(HypofuzzWebsocket):
    async def send_tests(self, tests: dict[str, Test]) -> None:
        from hypofuzz.dashboard.dashboard import COLLECTION_RESULT, TESTS

        assert COLLECTION_RESULT is not None

        event: SetStatusEvent = {
            "type": DashboardEventType.SET_STATUS,
            "count_tests": len(COLLECTION_RESULT.fuzz_targets),
            "count_tests_loaded": len(TESTS),
        }
        await self.send_event(event)

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
            if key in [
                DatabaseEventKey.FAILURE_SHRUNK_OBSERVATION,
                DatabaseEventKey.FAILURE_UNSHRUNK_OBSERVATION,
            ]:
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
            if key in [
                DatabaseEventKey.FAILURE_SHRUNK_OBSERVATION,
                DatabaseEventKey.FAILURE_UNSHRUNK_OBSERVATION,
                DatabaseEventKey.FAILURE_FIXED_OBSERVATION,
            ]:
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

    async def send_tests(self, tests: dict[str, Test]) -> None:
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
            elif key in [
                DatabaseEventKey.FAILURE_SHRUNK_OBSERVATION,
                DatabaseEventKey.FAILURE_UNSHRUNK_OBSERVATION,
            ]:
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
                return

        if event_type == "delete":
            if key in [
                DatabaseEventKey.FAILURE_SHRUNK_OBSERVATION,
                DatabaseEventKey.FAILURE_UNSHRUNK_OBSERVATION,
            ]:
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


async def broadcast_event(
    event_type: Literal["save", "delete"], key: DatabaseEventKey, value: Any
) -> None:
    # avoid error on websocket disconnecting during iteration
    for websocket in websockets.copy():
        await websocket.on_event(event_type, key, value)


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
