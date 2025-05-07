import dataclasses
import hashlib
import json
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, is_dataclass
from enum import Enum
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Literal, Optional

from hypothesis.database import (
    ExampleDatabase,
    choices_from_bytes,
    choices_to_bytes,
)
from hypothesis.internal.conjecture.choice import ChoiceT
from hypothesis.internal.conjecture.data import Status
from sortedcontainers import SortedList

if TYPE_CHECKING:
    from typing import TypeAlias

ChoicesT: "TypeAlias" = tuple[ChoiceT, ...]


class HypofuzzEncoder(json.JSONEncoder):
    def default(self, obj: object) -> object:
        if is_dataclass(obj) and not isinstance(obj, type):
            return dataclasses.asdict(obj)
        if isinstance(obj, SortedList):
            return list(obj)
        if isinstance(obj, Enum):
            return obj.value
        return super().default(obj)


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
    def from_json(data: dict) -> "WorkerIdentity":
        return WorkerIdentity(**data)

    def __repr__(self) -> str:
        return f"WorkerIdentity(uuid={self.uuid!r})"

    __str__ = __repr__


class ObservationStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    GAVE_UP = "gave_up"


@dataclass(frozen=True)
class Observation:
    # attributes from
    # https://hypothesis.readthedocs.io/en/latest/reference/integrations.html#test-case

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
    metadata: dict[str, Any]
    property: str
    run_start: int

    @staticmethod
    def from_json(data: dict) -> Optional["Observation"]:
        data = dict(data)
        # we disable observability coverage, but hypothesis still gives us a key
        # for it.
        if "coverage" in data:
            data.pop("coverage")
        try:
            data["status"] = ObservationStatus(data["status"])
            return Observation(**data)
        except Exception:
            return None


class Phase(Enum):
    GENERATE = "generate"
    REPLAY = "replay"
    DISTILL = "distill"
    SHRINK = "shrink"
    FAILED = "failed"


class StatusCounts(dict):
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


# * A report is an incremental progress marker which we don't want to delete,
#   because seeing intermediary stages in e.g. a graph is useful information
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
    worker: WorkerIdentity
    status_counts: StatusCounts
    branches: int
    since_new_cov: Optional[int]
    phase: Phase

    @staticmethod
    def from_json(data: dict) -> Optional["Report"]:
        data = dict(data)
        try:
            data["worker"] = WorkerIdentity.from_json(data["worker"])
            data["status_counts"] = StatusCounts(
                {Status(int(k)): v for k, v in data["status_counts"].items()}
            )
            data["phase"] = Phase(data["phase"])
            return Report(**data)
        except Exception:
            return None


reports_key = b".hypofuzz.reports"
observations_key = b".hypofuzz.observations"
corpus_key = b".hypofuzz.corpus"
failures_key = b".hypofuzz.failures"


@lru_cache(maxsize=512)
def corpus_observation_key(key: bytes, choices: ChoicesT) -> bytes:
    return (
        key
        + corpus_key
        + b"."
        + hashlib.sha1(choices_to_bytes(choices)).digest()
        + b".observation"
    )


def failure_key(key: bytes, *, shrunk: bool) -> bytes:
    return key + (b"" if shrunk else b".secondary")


@lru_cache(maxsize=512)
def failure_observation_key(key: bytes, choices: ChoicesT) -> bytes:
    return (
        key
        + failures_key
        + b"."
        + hashlib.sha1(choices_to_bytes(choices)).digest()
        + b".observation"
    )


def is_observation_key(key: bytes) -> bool:
    return key.endswith(observations_key)


def is_failure_observation_key(key: bytes) -> bool:
    return key.endswith(b".observation") and failures_key in key


def is_corpus_observation_key(key: bytes) -> bool:
    return key.endswith(b".observation") and corpus_key in key


class HypofuzzDatabase:
    def __init__(self, db: ExampleDatabase) -> None:
        self._db = db
        # track a per-test observability buffer, so we can discard when we go over
        self._obs_buffers: dict[bytes, deque[Observation]] = defaultdict(deque)

    def __str__(self) -> str:
        return f"HypofuzzDatabase({self._db!r})"

    __repr__ = __str__

    def _encode(self, data: Any) -> bytes:
        return bytes(json.dumps(data, cls=HypofuzzEncoder), "ascii")

    # standard (no key)

    def save(self, key: bytes, value: bytes) -> None:
        self._db.save(key, value)

    def fetch(self, key: bytes) -> Iterable[bytes]:
        yield from self._db.fetch(key)

    def delete(self, key: bytes, value: bytes) -> None:
        self._db.delete(key, value)

    # reports (reports_key)

    def save_report(self, key: bytes, report: Report) -> None:
        self.save(key + reports_key, self._encode(report))

    def delete_report(self, key: bytes, report: Report) -> None:
        self.delete(key + reports_key, self._encode(report))

    def fetch_reports(self, key: bytes) -> list[Report]:
        reports = [
            Report.from_json(json.loads(v)) for v in self.fetch(key + reports_key)
        ]
        return [r for r in reports if r is not None]

    # observations (observe_key)

    def save_observation(
        self, key: bytes, observation: Observation, *, discard_over: int
    ) -> None:
        obs_buffer = self._obs_buffers[key]
        if not obs_buffer:
            # If we don't have anything at all, load from the database - earliest
            # first so we drop those first
            obs_buffer.extend(
                sorted(
                    list(self.fetch_observations(key)),
                    key=lambda x: x.run_start,
                )
            )

        obs_buffer.append(observation)
        self.save(key + observations_key, self._encode(observation))

        # If we have more elements in the buffer than we need, clear them out.
        while len(obs_buffer) > discard_over:
            self.delete_observation(key, obs_buffer.popleft())

    def delete_observation(self, key: bytes, observation: Observation) -> None:
        self.delete(key + observations_key, self._encode(observation))

    def fetch_observations(self, key: bytes) -> Iterable[Observation]:
        for as_bytes in self.fetch(key + observations_key):
            if (observation := Observation.from_json(json.loads(as_bytes))) is not None:
                yield observation

    # corpus (corpus_key)

    def save_corpus(self, key: bytes, choices: ChoicesT) -> None:
        self.save(key + corpus_key, choices_to_bytes(choices))

    def delete_corpus(self, key: bytes, choices: ChoicesT) -> None:
        self.delete(key + corpus_key, choices_to_bytes(choices))

    def fetch_corpus(self, key: bytes) -> Iterable[ChoicesT]:
        for value in self.fetch(key + corpus_key):
            if (choices := choices_from_bytes(value)) is not None:
                yield choices

    # corpus observations (corpus_observe_key)

    def save_corpus_observation(
        self,
        key: bytes,
        choices: ChoicesT,
        observation: Observation,
        *,
        delete: bool = True,
    ) -> None:
        if not delete:
            self.save(corpus_observation_key(key, choices), self._encode(observation))
            return

        existing = list(self.fetch_corpus_observations(key, choices))
        self.save(corpus_observation_key(key, choices), self._encode(observation))
        for observation in existing:
            self.delete_corpus_observation(key, choices, observation)

    def delete_corpus_observation(
        self, key: bytes, choices: ChoicesT, observation: Observation
    ) -> None:
        self.delete(corpus_observation_key(key, choices), self._encode(observation))

    def fetch_corpus_observation(
        self,
        key: bytes,
        choices: ChoicesT,
    ) -> Optional[Observation]:
        # We expect there to be only a single entry. If there are multiple, we
        # arbitrarily pick one to return.
        observations = iter(self.fetch(corpus_observation_key(key, choices)))
        try:
            value = next(observations)
        except StopIteration:
            return None
        return Observation.from_json(json.loads(value))

    def fetch_corpus_observations(
        self,
        key: bytes,
        choices: ChoicesT,
    ) -> Iterable[Observation]:
        for value in self.fetch(corpus_observation_key(key, choices)):
            if (observation := Observation.from_json(json.loads(value))) is not None:
                yield observation

    # failures (failures_key)

    def save_failure(self, key: bytes, choices: ChoicesT, *, shrunk: bool) -> None:
        self.save(failure_key(key, shrunk=shrunk), choices_to_bytes(choices))

    def delete_failure(self, key: bytes, choices: ChoicesT, *, shrunk: bool) -> None:
        self.delete(failure_key(key, shrunk=shrunk), choices_to_bytes(choices))

    def fetch_failures(self, key: bytes, *, shrunk: bool) -> Iterable[ChoicesT]:
        for value in self.fetch(failure_key(key, shrunk=shrunk)):
            if (choices := choices_from_bytes(value)) is not None:
                yield choices

    # failure observation (failure_observation_key)

    def save_failure_observation(
        self,
        key: bytes,
        choices: ChoicesT,
        observation: Observation,
        *,
        delete: bool = True,
    ) -> None:
        if not delete:
            self.save(failure_observation_key(key, choices), self._encode(observation))
            return

        existing = list(self.fetch_failure_observations(key, choices))
        self.save(failure_observation_key(key, choices), self._encode(observation))
        for observation in existing:
            self.delete_failure_observation(key, choices, observation)

    def delete_failure_observation(
        self, key: bytes, choices: ChoicesT, observation: Observation
    ) -> None:
        self.delete(failure_observation_key(key, choices), self._encode(observation))

    def fetch_failure_observation(
        self, key: bytes, choices: ChoicesT
    ) -> Optional[Observation]:
        observations = iter(self.fetch(failure_observation_key(key, choices)))
        try:
            value = next(observations)
        except StopIteration:
            return None
        return Observation.from_json(json.loads(value))

    def fetch_failure_observations(
        self, key: bytes, choices: ChoicesT
    ) -> Iterable[Observation]:
        for value in self.fetch(failure_observation_key(key, choices)):
            if (observation := Observation.from_json(json.loads(value))) is not None:
                yield observation


@dataclass
class ReportOffsets:
    status_counts: dict[str, StatusCounts]
    elapsed_time: dict[str, float]


@dataclass
class LinearReports:
    reports: list[Report]
    offsets: ReportOffsets


def linearize_reports(reports: list[Report]) -> LinearReports:
    """
    Given an (arbitrarily ordered) list of reports, potentially from different
    workers and potentially with overlapping durations, reconstruct a best-effort
    linearization suitable for e.g. display in the dashboard.
    """
    # The linearization algorithm is as follows:
    # * Track the total number of inputs and the total elapsed time of the
    #   current linearized history.
    # * Examine reports in sorted timestamp order. Compute the new status_counts c
    #   and new elapsed_time t relative to the previous report from that worker.
    # * Append a new report to the linearized history, which is the same as the
    #   actual report but with status counts linearized_status_counts + c and
    #   elapsed time linearized_elapsed_time + t.
    #
    # We could improve lineariztion for time periods with overlapping workers by
    # taking the maximum of any coverage achieved in that interval, if all the
    # workers are fuzzing the same code state. If the workers have different code
    # states (e.g. a different git hash), then we have no choice but to treat
    # the reported coverage as canonical and accept coverage jitter in the graph.

    total_statuses = StatusCounts(dict.fromkeys(Status, 0))
    total_elapsed_time = 0.0
    linearized_reports = []
    # we track a running total of status counts and elapsed_time for each worker.
    # This lets us compute new status counts and elapsed_time for each report,
    # relative to the previous report.
    #
    # We could equivalently store statuses_new and elapsed_time_new on the reports.
    # (but then deletion or loss of arbitrary reports becomes unsound without fixing
    # up the subsequent report).
    offsets_statuses: dict[str, StatusCounts] = defaultdict(
        lambda: StatusCounts(dict.fromkeys(Status, 0))
    )
    offsets_elapsed_time: dict[str, float] = defaultdict(float)
    # We sort by timestamp, and rely on the invariant that reports from an
    # individual worker always monotonically increase in both status counts and
    # elapsed_time as the timestamp increases, so that sorting by timestamp is
    # enough to sort by all three attributes (within an individual worker).
    for report in sorted(reports, key=lambda report: report.timestamp):
        statuses_diff = report.status_counts - offsets_statuses[report.worker.uuid]
        elapsed_time_diff = (
            report.elapsed_time - offsets_elapsed_time[report.worker.uuid]
        )
        assert all(count >= 0 for count in statuses_diff.values())
        assert elapsed_time_diff >= 0

        if report.phase is not Phase.REPLAY:
            linearized_report = dataclasses.replace(
                report,
                status_counts=total_statuses + statuses_diff,
                elapsed_time=total_elapsed_time + elapsed_time_diff,
            )
            linearized_reports.append(linearized_report)

        # TODO we should probably NOT count inputs or elapsed time from
        # Phase.REPLAY, because this is not time we spent looking for bugs?
        # Be careful when factoring this into e.g. "cost per bug", though - it's
        # still cpu time being paid for.
        total_statuses += statuses_diff
        total_elapsed_time += elapsed_time_diff
        offsets_statuses[report.worker.uuid] = report.status_counts
        offsets_elapsed_time[report.worker.uuid] = report.elapsed_time

    return LinearReports(
        reports=linearized_reports,
        offsets=ReportOffsets(
            status_counts=dict(offsets_statuses),
            elapsed_time=dict(offsets_elapsed_time),
        ),
    )
