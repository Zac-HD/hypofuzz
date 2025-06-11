from enum import IntEnum
from typing import Any, Literal, Optional, TypedDict, Union

from hypofuzz.dashboard.test import Test
from hypofuzz.database import (
    Observation,
    ObservationStatus,
    Phase,
    Report,
    StatusCounts,
)


class DashboardObservationMetadata(TypedDict):
    traceback: Optional[str]
    reproduction_decorator: Optional[str]


class DashboardObservation(TypedDict):
    type: str
    status: ObservationStatus
    status_reason: str
    representation: str
    arguments: dict[str, Any]
    how_generated: str
    features: dict[str, Any]
    timing: dict[str, Any]
    metadata: DashboardObservationMetadata
    property: str
    run_start: float


def dashboard_observation(observation: Observation) -> DashboardObservation:
    return {
        "type": observation.type,
        "status": observation.status,
        "status_reason": observation.status_reason,
        "representation": observation.representation,
        "arguments": observation.arguments,
        "how_generated": observation.how_generated,
        "features": observation.features,
        "timing": observation.timing,
        "metadata": {
            "traceback": observation.metadata.traceback,
            "reproduction_decorator": observation.metadata.reproduction_decorator,
        },
        "property": observation.property,
        "run_start": observation.run_start,
    }


class DashboardReport(TypedDict):
    elapsed_time: float
    status_counts: StatusCounts
    behaviors: int
    fingerprints: int
    timestamp: float
    since_new_branch: Optional[int]
    phase: Phase


def dashboard_report(report: Report) -> DashboardReport:
    return {
        "elapsed_time": report.elapsed_time,
        "status_counts": report.status_counts,
        "behaviors": report.behaviors,
        "fingerprints": report.fingerprints,
        "timestamp": report.timestamp,
        "since_new_branch": report.since_new_branch,
        "phase": report.phase,
    }


# We only return this in api routes. It's not actually used by or sent to
# DataProvider.tsx.
class DashboardTest(TypedDict):
    database_key: str
    nodeid: str
    rolling_observations: list[DashboardObservation]
    corpus_observations: list[DashboardObservation]
    failure: Optional[DashboardObservation]
    reports_by_worker: dict[str, list[DashboardReport]]


def dashboard_test(test: Test) -> DashboardTest:
    return {
        "database_key": test.database_key,
        "nodeid": test.nodeid,
        "rolling_observations": [
            dashboard_observation(obs) for obs in test.rolling_observations
        ],
        "corpus_observations": [
            dashboard_observation(obs) for obs in test.corpus_observations
        ],
        "failure": dashboard_observation(test.failure) if test.failure else None,
        "reports_by_worker": {
            worker_uuid: [dashboard_report(report) for report in reports]
            for worker_uuid, reports in test.reports_by_worker.items()
        },
    }


# keep in sync with DashboardEventType in DataProvider.tsx
class DashboardEventType(IntEnum):
    # minimize header frame overhead with a shared IntEnum definition between
    # python and ts.
    ADD_TESTS = 1
    ADD_REPORTS = 2
    ADD_OBSERVATIONS = 3
    SET_FAILURE = 4


ObservationType = Literal["rolling", "corpus"]


# keep in sync with TestsAction in DataProvider.tsx
class AddTestsTest(TypedDict):
    database_key: str
    nodeid: str
    failure: Optional[Observation]


class AddTestsEvent(TypedDict):
    type: Literal[DashboardEventType.ADD_TESTS]
    tests: list[AddTestsTest]


class AddReportsEvent(TypedDict):
    type: Literal[DashboardEventType.ADD_REPORTS]
    nodeid: str
    worker_uuid: str
    reports: list[DashboardReport]


class AddObservationsEvent(TypedDict):
    type: Literal[DashboardEventType.ADD_OBSERVATIONS]
    nodeid: str
    observation_type: ObservationType
    observations: list[DashboardObservation]


class SetFailureEvent(TypedDict):
    type: Literal[DashboardEventType.SET_FAILURE]
    nodeid: str
    failure: Optional[DashboardObservation]


DashboardEventT = Union[
    AddTestsEvent,
    AddReportsEvent,
    AddObservationsEvent,
    SetFailureEvent,
]
