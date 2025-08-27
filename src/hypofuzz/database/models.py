import json
from dataclasses import dataclass
from enum import Enum
from typing import (
    Any,
    Literal,
    Optional,
    Union,
)

from hypothesis.internal.conjecture.data import Status
from hypothesis.internal.observability import (
    ObservationMetadata as HypothesisObservationMetadata,
    PredicateCounts,
    TestCaseObservation,
)

from hypofuzz.utils import convert_to_fuzzjson


@dataclass(frozen=True)
class WorkerIdentity:
    uuid: str
    operating_system: str
    python_version: str
    hypothesis_version: str
    hypofuzz_version: str
    pid: int
    hostname: str
    pod_name: Optional[str]
    pod_namespace: Optional[str]
    node_name: Optional[str]
    pod_ip: Optional[str]
    container_id: Optional[str]
    git_hash: Optional[str]

    @staticmethod
    def from_json(data: bytes) -> Optional["WorkerIdentity"]:
        try:
            return WorkerIdentity(**json.loads(data))
        except Exception:
            return None

    def __repr__(self) -> str:
        return f"WorkerIdentity(uuid={self.uuid!r})"

    __str__ = __repr__


class ObservationStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    GAVE_UP = "gave_up"


class Stability(Enum):
    STABLE = "stable"
    UNSTABLE = "unstable"
    # we'll want a third "semistable" status eventually, to represent first-time
    # cache hits (with behaviors: A B B B ... ).


# only the subset of the metadata that we store from HypothesisObservation.
@dataclass(frozen=True)
class ObservationMetadata:
    traceback: Optional[str]
    reproduction_decorator: Optional[str]
    predicates: dict[str, PredicateCounts]
    backend: dict[str, Any]
    sys_argv: list[str]
    os_getpid: int
    imported_at: float
    data_status: "Status"

    @classmethod
    def from_hypothesis(
        cls, metadata: HypothesisObservationMetadata
    ) -> "ObservationMetadata":
        return cls(
            traceback=metadata.traceback,
            reproduction_decorator=metadata.reproduction_decorator,
            predicates=metadata.predicates,
            backend=metadata.backend,
            sys_argv=metadata.sys_argv,
            os_getpid=metadata.os_getpid,
            imported_at=metadata.imported_at,
            data_status=metadata.data_status,
        )


@dataclass(frozen=True)
class Observation:
    # we're only storing test_case reports for now. We may store information
    # messages in the future as well.
    type: Literal["test_case"]
    status: ObservationStatus
    status_reason: str
    representation: str
    arguments: dict[str, Any]
    how_generated: str
    features: dict[str, Any]
    timing: dict[str, Any]
    metadata: ObservationMetadata
    property: str
    run_start: float
    # stability == None means we don't know the stability, because we didn't
    # re-execute this observation
    stability: Optional[Stability]

    @classmethod
    def from_hypothesis(
        cls, observation: TestCaseObservation, stability: Optional[Stability] = None
    ) -> "Observation":
        return cls(
            type=observation.type,
            status=ObservationStatus(observation.status),
            status_reason=observation.status_reason,
            representation=observation.representation,
            arguments=convert_to_fuzzjson(observation.arguments),
            how_generated=observation.how_generated,
            features=convert_to_fuzzjson(observation.features),
            timing=observation.timing,
            metadata=ObservationMetadata.from_hypothesis(observation.metadata),
            property=observation.property,
            run_start=observation.run_start,
            stability=stability,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any], /) -> "Observation":
        # we disable observability coverage, so discard the empty key
        data.pop("coverage", None)
        data["status"] = ObservationStatus(data["status"])
        if data["stability"] is not None:
            data["stability"] = Stability(data["stability"])
        data["metadata"]["predicates"] = {
            k: PredicateCounts(satisfied=v["satisfied"], unsatisfied=v["unsatisfied"])
            for k, v in data["metadata"]["predicates"].items()
        }
        data["metadata"] = ObservationMetadata(**data["metadata"])
        return cls(**data)

    @classmethod
    def from_json(cls, encoded: bytes, /) -> Optional["Observation"]:
        try:
            return cls.from_dict(json.loads(encoded))
        except Exception:
            return None


class Phase(Enum):
    GENERATE = "generate"
    REPLAY = "replay"
    DISTILL = "distill"
    SHRINK = "shrink"
    FAILED = "failed"


class StatusCounts(dict):
    def __init__(self, value: Optional[dict[Status, int]] = None) -> None:
        if value is None:
            value = dict.fromkeys(Status, 0)
        super().__init__(value)

    # add rich operators to the otherwise plain-dict of report.status_counts.
    def __add__(self, other: "StatusCounts") -> "StatusCounts":
        assert self.keys() == other.keys()
        result = StatusCounts(self)
        for status in self:
            result[status] += other[status]
        return result

    def __sub__(self, other: "StatusCounts") -> "StatusCounts":
        assert self.keys() == other.keys()
        result = StatusCounts(self)
        for status in self:
            result[status] -= other[status]
        return result

    def __le__(self, other: "StatusCounts") -> bool:
        assert self.keys() == other.keys()
        return all(self[status] <= other[status] for status in self)

    def __lt__(self, other: "StatusCounts") -> bool:
        assert self.keys() == other.keys()
        return all(self[status] < other[status] for status in self)


@dataclass(frozen=True)
class Report:
    """
    An incremental progress marker of a fuzzing campaign. We save a new report
    whenever we discover new coverage, switch phases, or something particularly
    interesting happens.
    """

    database_key: str
    nodeid: str
    elapsed_time: float
    timestamp: float
    worker_uuid: str
    status_counts: StatusCounts
    behaviors: int
    fingerprints: int
    since_new_behavior: Optional[int]
    phase: Phase

    def __post_init__(self) -> None:
        assert self.elapsed_time >= 0, f"{self.elapsed_time=}"
        assert self.behaviors >= 0, f"{self.behaviors=}"
        assert self.fingerprints >= 0, f"{self.fingerprints=}"
        assert self.phase in Phase, f"{self.phase=}"
        if self.since_new_behavior is not None:
            assert self.since_new_behavior >= 0, f"{self.since_new_behavior=}"

    @staticmethod
    def from_json(encoded: bytes, /) -> Optional["Report"]:
        try:
            data = json.loads(encoded)
            data["status_counts"] = StatusCounts(
                {Status(int(k)): v for k, v in data["status_counts"].items()}
            )
            data["phase"] = Phase(data["phase"])
            # migration for old dbs
            if "since_new_branch" in data:
                data["since_new_behavior"] = data.pop("since_new_branch")
            return Report(**data)
        except Exception:
            return None


@dataclass(frozen=True)
class ReportWithDiff(Report):
    # This fields are not stored in the database, but are computed for an
    # individual Report, relative to another Report.
    status_counts_diff: StatusCounts
    elapsed_time_diff: float
    # Clock updates due to e.g. NTP can make time.time() non-monotonic, so
    # to preserve ordering in edge cases we define `timestamp_monotonic` as
    # `max(time.time(), previous_timestamp_monotonic + elapsed_time_diff)`.
    timestamp_monotonic: float

    def __post_init__(self) -> None:
        assert all(
            count >= 0 for count in self.status_counts_diff.values()
        ), self.status_counts_diff
        assert self.elapsed_time_diff >= 0.0
        assert self.timestamp_monotonic >= 0.0

    @classmethod
    def from_reports(
        cls,
        report: Report,
        *,
        last_worker_report: Union["ReportWithDiff", None],
    ) -> "ReportWithDiff":
        last_status_counts = (
            StatusCounts()
            if last_worker_report is None
            else last_worker_report.status_counts
        )
        last_elapsed_time = (
            0.0 if last_worker_report is None else last_worker_report.elapsed_time
        )
        status_counts_diff = report.status_counts - last_status_counts
        elapsed_time_diff = report.elapsed_time - last_elapsed_time
        timestamp_monotonic = (
            report.timestamp
            if last_worker_report is None
            else max(
                report.timestamp,
                last_worker_report.timestamp_monotonic + elapsed_time_diff,
            )
        )

        assert elapsed_time_diff >= 0.0
        # note: timestamp_monotonic might be negative, if the initial
        # report.timestamp was negative, because someone set their system clock
        # to before 1969.

        return cls(
            database_key=report.database_key,
            nodeid=report.nodeid,
            elapsed_time=report.elapsed_time,
            timestamp=report.timestamp,
            worker_uuid=report.worker_uuid,
            status_counts=report.status_counts,
            behaviors=report.behaviors,
            fingerprints=report.fingerprints,
            since_new_behavior=report.since_new_behavior,
            phase=report.phase,
            status_counts_diff=status_counts_diff,
            elapsed_time_diff=elapsed_time_diff,
            timestamp_monotonic=timestamp_monotonic,
        )


class FailureState(Enum):
    SHRUNK = "shrunk"
    UNSHRUNK = "unshrunk"
    FIXED = "fixed"


@dataclass(frozen=True)
class FatalFailure:
    nodeid: str
    traceback: str

    @staticmethod
    def from_json(data: bytes) -> Optional["FatalFailure"]:
        try:
            return FatalFailure(**json.loads(data))
        except Exception:
            return None
