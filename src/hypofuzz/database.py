import dataclasses
import hashlib
import json
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, field, is_dataclass
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

    @classmethod
    def from_dict(cls, data: dict[str, Any], /) -> "Observation":
        # we disable observability coverage, so discard the empty key
        data.pop("coverage", None)
        data["status"] = ObservationStatus(data["status"])
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
    worker: WorkerIdentity
    status_counts: StatusCounts
    branches: int
    since_new_branch: Optional[int]
    phase: Phase

    # This fields are not stored in the database, but are computed for an
    # individual Report, relative to another Report.
    status_counts_diff: Optional[StatusCounts] = field(default=None)
    elapsed_time_diff: Optional[float] = field(default=None)
    # The timestamp of consecutive reports is not always monotonic - due to
    # daylight savings time, for example, or merely NTP clock updates. We therefore
    # store a separate timestamp_monotonic, which uses timestamp if the timestamp
    # is monotonic relative to the previous report, and otherwise
    # previous_report.timestamp_monotonic + elapsed_time_diff.
    timestamp_monotonic: Optional[float] = field(default=None)

    def __post_init__(self) -> None:
        assert self.elapsed_time >= 0, f"{self.elapsed_time=}"
        assert self.branches >= 0, f"{self.branches=}"
        assert self.phase in Phase, f"{self.phase=}"
        if self.since_new_branch is not None:
            assert self.since_new_branch >= 0, f"{self.since_new_branch=}"

    @staticmethod
    def from_json(encoded: bytes, /) -> Optional["Report"]:
        try:
            data = json.loads(encoded)
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
        reports = [Report.from_json(v) for v in self.fetch(key + reports_key)]
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
        try:
            return next(iter(self.fetch_corpus_observations(key, choices)))
        except StopIteration:
            return None

    def fetch_corpus_observations(
        self,
        key: bytes,
        choices: ChoicesT,
    ) -> Iterable[Observation]:
        for value in self.fetch(corpus_observation_key(key, choices)):
            if observation := Observation.from_json(value):
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
        try:
            return next(iter(self.fetch_failure_observations(key, choices)))
        except StopIteration:
            return None

    def fetch_failure_observations(
        self, key: bytes, choices: ChoicesT
    ) -> Iterable[Observation]:
        for value in self.fetch(failure_observation_key(key, choices)):
            if observation := Observation.from_json(value):
                yield observation
