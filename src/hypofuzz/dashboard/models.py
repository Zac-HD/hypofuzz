from dataclasses import dataclass
from enum import IntEnum
from typing import Any, ClassVar, Literal, Optional, TypedDict, Union

from hypofuzz.dashboard.test import Test
from hypofuzz.database import (
    FailureState,
    Observation,
    ObservationStatus,
    Phase,
    Report,
    Stability,
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
    stability: Optional[Stability]


class Failure(TypedDict):
    state: FailureState
    observation: DashboardObservation


class DashboardReport(TypedDict):
    elapsed_time: float
    status_counts: StatusCounts
    behaviors: int
    fingerprints: int
    timestamp: float
    since_new_behavior: Optional[int]
    phase: Phase


# We only return this in api routes. It's not actually used by or sent to
# DataProvider.tsx.
class DashboardTest(TypedDict):
    database_key: str
    nodeid: str
    rolling_observations: list[DashboardObservation]
    corpus_observations: list[DashboardObservation]
    failures: dict[str, Failure]
    fatal_failure: Optional[str]
    reports_by_worker: dict[str, list[DashboardReport]]
    stability: Optional[float]


# keep in sync with DashboardEventType in DataProvider.tsx
class DashboardEventType(IntEnum):
    # minimize header frame overhead with a shared IntEnum definition between
    # python and ts.
    SET_STATUS = 1
    ADD_TESTS = 2
    ADD_REPORTS = 3
    ADD_OBSERVATIONS = 4
    ADD_FAILURES = 5
    SET_FAILURES = 6
    TEST_LOAD_FINISHED = 7


ObservationType = Literal["rolling", "corpus"]


@dataclass
class DashboardEvent:
    type: ClassVar[DashboardEventType]


# keep in sync with TestsAction in DataProvider.tsx
class AddTestsTest(TypedDict):
    database_key: str
    nodeid: str
    failures: dict[str, Failure]
    fatal_failure: Optional[str]
    stability: Optional[float]


@dataclass
class AddTestsEvent(DashboardEvent):
    type = DashboardEventType.ADD_TESTS
    tests: list[AddTestsTest]


@dataclass
class AddReportsEvent(DashboardEvent):
    type = DashboardEventType.ADD_REPORTS
    nodeid: str
    worker_uuid: str
    reports: list[DashboardReport]


@dataclass
class AddObservationsEvent(DashboardEvent):
    type = DashboardEventType.ADD_OBSERVATIONS
    nodeid: str
    observation_type: ObservationType
    observations: list[DashboardObservation]


@dataclass
class AddFailuresEvent(DashboardEvent):
    type = DashboardEventType.ADD_FAILURES
    nodeid: str
    failures: dict[str, Failure]


@dataclass
class SetFailuresEvent(DashboardEvent):
    type = DashboardEventType.SET_FAILURES
    nodeid: str
    failures: dict[str, Failure]


@dataclass
class SetStatusEvent(DashboardEvent):
    type = DashboardEventType.SET_STATUS
    count_tests: int
    count_tests_loaded: int


@dataclass
class TestLoadFinishedEvent(DashboardEvent):
    type = DashboardEventType.TEST_LOAD_FINISHED
    nodeid: str


DashboardEventT = Union[
    AddTestsEvent,
    AddReportsEvent,
    AddObservationsEvent,
    AddFailuresEvent,
    SetFailuresEvent,
    SetStatusEvent,
    TestLoadFinishedEvent,
]


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
        "stability": observation.stability,
    }


def dashboard_report(report: Report) -> DashboardReport:
    return {
        "elapsed_time": report.elapsed_time,
        "status_counts": report.status_counts,
        "behaviors": report.behaviors,
        "fingerprints": report.fingerprints,
        "timestamp": report.timestamp,
        "since_new_behavior": report.since_new_behavior,
        "phase": report.phase,
    }


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
        "failures": dashboard_failures(test.failures),
        "fatal_failure": test.fatal_failure,
        "reports_by_worker": {
            worker_uuid: [dashboard_report(report) for report in reports]
            for worker_uuid, reports in test.reports_by_worker.items()
        },
        "stability": test.stability,
    }


def dashboard_failures(
    failures: dict[str, tuple[FailureState, Observation]],
) -> dict[str, Failure]:
    return {
        interesting_origin: Failure(
            state=state, observation=dashboard_observation(failure)
        )
        for interesting_origin, (state, failure) in failures.items()
    }
