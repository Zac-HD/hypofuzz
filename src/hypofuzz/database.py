import dataclasses
import hashlib
import json
from base64 import b64decode, b64encode
from collections import defaultdict, deque
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, is_dataclass
from enum import Enum
from functools import lru_cache
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    Optional,
    Protocol,
    TypeVar,
    Union,
    overload,
)

from hypothesis.database import (
    ExampleDatabase,
    ListenerEventT,
    choices_from_bytes,
    choices_to_bytes,
)
from hypothesis.internal.conjecture.choice import ChoiceT
from hypothesis.internal.conjecture.data import Status
from hypothesis.internal.observability import (
    ObservationMetadata as HypothesisObservationMetadata,
    PredicateCounts,
    TestCaseObservation,
)
from sortedcontainers import SortedList

if TYPE_CHECKING:
    from typing import TypeAlias

ChoicesT: "TypeAlias" = tuple[ChoiceT, ...]
T = TypeVar("T", covariant=True)


class HashableIterable(Protocol[T]):
    def __hash__(self) -> int: ...
    def __iter__(self) -> Iterator[T]: ...


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

    @classmethod
    def from_hypothesis(cls, observation: TestCaseObservation) -> "Observation":
        return cls(
            type=observation.type,
            status=ObservationStatus(observation.status),
            status_reason=observation.status_reason,
            representation=observation.representation,
            arguments=observation.arguments,
            how_generated=observation.how_generated,
            features=observation.features,
            timing=observation.timing,
            metadata=ObservationMetadata.from_hypothesis(observation.metadata),
            property=observation.property,
            run_start=observation.run_start,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any], /) -> "Observation":
        # we disable observability coverage, so discard the empty key
        data.pop("coverage", None)
        data["status"] = ObservationStatus(data["status"])
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


class DatabaseEventKey(Enum):
    REPORT = "report"
    FAILURE_OBSERVATION = "failure_observation"
    ROLLING_OBSERVATION = "rolling_observation"
    CORPUS_OBSERVATION = "corpus_observation"
    CORPUS = "corpus"
    FAILURE = "failure"


@dataclass(frozen=True)
class DatabaseEvent:
    type: Literal["save", "delete"]
    database_key: bytes
    key: DatabaseEventKey
    value: Any

    # depends on hypothesis.internal.reflection.function_digest, which uses
    # hashlib.sha384 (384 bits = 48 bytes)
    DATABASE_KEY_LENGTH = 48

    @classmethod
    def from_event(cls, event: ListenerEventT, /) -> Optional["DatabaseEvent"]:
        # placate mypy
        key: Any
        value: Any
        parse: Any
        (event_type, (key, value)) = event
        if b"." not in key or len(key) <= cls.DATABASE_KEY_LENGTH:
            return None

        # indexing into bytes converts to int
        assert key[cls.DATABASE_KEY_LENGTH] == ord("."), key
        database_key = key[: cls.DATABASE_KEY_LENGTH]
        if key.endswith(reports_key):
            key = DatabaseEventKey.REPORT
            parse = Report.from_json
        elif key.endswith(corpus_key):
            key = DatabaseEventKey.CORPUS
            parse = choices_from_bytes
        elif key.endswith(failures_key):
            key = DatabaseEventKey.FAILURE
            parse = choices_from_bytes
        elif key.endswith(observations_key):
            parse = Observation.from_json
            key = DatabaseEventKey.ROLLING_OBSERVATION
        elif is_failure_observation_key(key):
            key = DatabaseEventKey.FAILURE_OBSERVATION
            parse = Observation.from_json
        elif is_corpus_observation_key(key):
            key = DatabaseEventKey.CORPUS_OBSERVATION
            parse = Observation.from_json
        else:
            return None

        if event_type == "save":
            assert value is not None

        # value might be None for event_type == "delete"
        if value is not None:
            value = parse(value)
            if value is None:
                # invalid parse
                return None

        return DatabaseEvent(
            type=event_type,
            database_key=database_key,
            key=key,
            value=value,
        )


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
    since_new_branch: Optional[int]
    phase: Phase

    def __post_init__(self) -> None:
        assert self.elapsed_time >= 0, f"{self.elapsed_time=}"
        assert self.behaviors >= 0, f"{self.behaviors=}"
        assert self.fingerprints >= 0, f"{self.fingerprints=}"
        assert self.phase in Phase, f"{self.phase=}"
        if self.since_new_branch is not None:
            assert self.since_new_branch >= 0, f"{self.since_new_branch=}"

    @staticmethod
    def from_json(encoded: bytes, /) -> Optional["Report"]:
        try:
            data = json.loads(encoded)
            data["status_counts"] = StatusCounts(
                {Status(int(k)): v for k, v in data["status_counts"].items()}
            )
            data["phase"] = Phase(data["phase"])
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
        assert all(count >= 0 for count in self.status_counts_diff.values())
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
            since_new_branch=report.since_new_branch,
            phase=report.phase,
            status_counts_diff=status_counts_diff,
            elapsed_time_diff=elapsed_time_diff,
            timestamp_monotonic=timestamp_monotonic,
        )


test_keys_key = b"hypofuzz.test_keys"
reports_key = b".hypofuzz.reports"
observations_key = b".hypofuzz.observations"
corpus_key = b".hypofuzz.corpus"
worker_identity_key = b".hypofuzz.worker_identity"
failures_key = b".hypofuzz.failures"


def get_worker_identity_key(key: bytes, uuid: str) -> bytes:
    return key + worker_identity_key + b"." + uuid.encode("ascii")


# `choices` required to be hashable for @lru_cache
@lru_cache(maxsize=512)
def corpus_observation_key(
    key: bytes, choices: Union[HashableIterable[ChoiceT], bytes]
) -> bytes:
    choices_bytes = choices if isinstance(choices, bytes) else choices_to_bytes(choices)
    return (
        key + corpus_key + b"." + hashlib.sha1(choices_bytes).digest() + b".observation"
    )


def failure_key(key: bytes, *, shrunk: bool) -> bytes:
    return key + (b"" if shrunk else b".secondary")


@lru_cache(maxsize=512)
def failure_observation_key(
    key: bytes, choices: Union[HashableIterable[ChoiceT], bytes]
) -> bytes:
    choices_bytes = choices if isinstance(choices, bytes) else choices_to_bytes(choices)
    return (
        key
        + failures_key
        + b"."
        + hashlib.sha1(choices_bytes).digest()
        + b".observation"
    )


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
        for value in self.fetch(key + observations_key):
            if observation := Observation.from_json(value):
                yield observation

    # corpus (corpus_key)

    def save_corpus(self, key: bytes, choices: Iterable[ChoiceT]) -> None:
        self.save(key + corpus_key, choices_to_bytes(choices))

    def delete_corpus(self, key: bytes, choices: Iterable[ChoiceT]) -> None:
        self.delete(key + corpus_key, choices_to_bytes(choices))

    @overload
    def fetch_corpus(
        self, key: bytes, *, as_bytes: Literal[False] = False
    ) -> Iterable[ChoicesT]: ...

    @overload
    def fetch_corpus(
        self, key: bytes, *, as_bytes: Literal[True]
    ) -> Iterable[bytes]: ...

    def fetch_corpus(
        self, key: bytes, *, as_bytes: bool = False
    ) -> Iterable[Union[ChoicesT, bytes]]:
        for value in self.fetch(key + corpus_key):
            if as_bytes:
                yield value
            elif (choices := choices_from_bytes(value)) is not None:
                yield choices

    def _check_observation(self, observation: Observation) -> None:
        # notably, not Hypothesis{Observation, Metadata}
        assert isinstance(observation, Observation)
        assert isinstance(observation.metadata, ObservationMetadata)

    # corpus observations (corpus_observe_key)

    def save_corpus_observation(
        self,
        key: bytes,
        choices: HashableIterable[ChoiceT],
        observation: Observation,
        *,
        delete: bool = True,
    ) -> None:
        self._check_observation(observation)
        if not delete:
            self.save(corpus_observation_key(key, choices), self._encode(observation))
            return

        existing = list(self.fetch_corpus_observations(key, choices))
        self.save(corpus_observation_key(key, choices), self._encode(observation))
        for observation in existing:
            self.delete_corpus_observation(key, choices, observation)

    def delete_corpus_observation(
        self, key: bytes, choices: HashableIterable[ChoiceT], observation: Observation
    ) -> None:
        self._check_observation(observation)
        self.delete(corpus_observation_key(key, choices), self._encode(observation))

    def fetch_corpus_observation(
        self,
        key: bytes,
        choices: Union[HashableIterable[ChoiceT], bytes],
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
        choices: Union[HashableIterable[ChoiceT], bytes],
    ) -> Iterable[Observation]:
        for value in self.fetch(corpus_observation_key(key, choices)):
            if observation := Observation.from_json(value):
                yield observation

    # failures (failure_key)

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
        self._check_observation(observation)
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
        self._check_observation(observation)
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

    # worker identity (worker_identity_key)

    def save_worker_identity(self, key: bytes, worker: WorkerIdentity) -> None:
        self.save(get_worker_identity_key(key, worker.uuid), self._encode(worker))

    def delete_worker_identity(self, key: bytes, worker: WorkerIdentity) -> None:
        self.delete(get_worker_identity_key(key, worker.uuid), self._encode(worker))

    def fetch_worker_identities(
        self, key: bytes, worker: WorkerIdentity
    ) -> Iterable[WorkerIdentity]:
        for value in self.fetch(get_worker_identity_key(key, worker.uuid)):
            if worker_identity := WorkerIdentity.from_json(value):
                yield worker_identity

    def fetch_worker_identity(
        self, key: bytes, worker: WorkerIdentity
    ) -> Optional[WorkerIdentity]:
        try:
            return next(iter(self.fetch_worker_identities(key, worker)))
        except StopIteration:
            return None


@overload
def convert_db_key(key: str, *, to: Literal["bytes"]) -> bytes: ...


@overload
def convert_db_key(key: bytes, *, to: Literal["str"]) -> str: ...


def convert_db_key(
    key: Union[str, bytes], *, to: Literal["str", "bytes"]
) -> Union[str, bytes]:
    if to == "str":
        assert isinstance(key, bytes)
        return b64encode(key).decode("ascii")
    elif to == "bytes":
        assert isinstance(key, str)
        return b64decode(key.encode("ascii"))
    else:
        raise ValueError(f"Invalid conversion {to=}")
