import abc
import dataclasses
import hashlib
import json
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, is_dataclass
from enum import Enum
from functools import lru_cache
from typing import (
    Any,
    Callable,
    Literal,
    Optional,
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
from sortedcontainers import SortedList

from hypofuzz.database.models import (
    FailureState,
    FatalFailure,
    Observation,
    ObservationMetadata,
    Report,
    WorkerIdentity,
)
from hypofuzz.database.utils import ChoicesT, HashableIterable

test_keys_key = b"hypofuzz.test_keys"
# a set of all known worker_uuids
worker_uuids_key = b"hypofuzz.worker_uuids"
# maps worker_uuid to a singleton worker identity
worker_identity_key = b"hypofuzz.worker_identity"

reports_key = b".hypofuzz.reports"
rolling_observations_key = b".hypofuzz.observations"
corpus_key = b".hypofuzz.corpus"
failures_key = b".hypofuzz.failures"
fatal_failure_key = b".hypofuzz.fatal_failure"


def _encode(data: Any) -> bytes:
    return bytes(json.dumps(data, cls=HypofuzzEncoder), "ascii")


def _check_observation(observation: Observation) -> None:
    # notably, not Hypothesis{Observation, Metadata}
    assert isinstance(observation, Observation)
    assert isinstance(observation.metadata, ObservationMetadata)


@lru_cache(maxsize=512)
def corpus_observation_key(
    key: bytes,
    # `choices` required to be hashable for @lru_cache
    choices: Union[HashableIterable[ChoiceT], bytes],
) -> bytes:
    choices_bytes = choices if isinstance(choices, bytes) else choices_to_bytes(choices)
    return (
        key + corpus_key + b"." + hashlib.sha1(choices_bytes).digest() + b".observation"
    )


def _failure_postfix(*, state: FailureState) -> bytes:
    # note that the postfixes here are different from failure_observation_key,
    # because the failure choice sequence keys have to line up with hypothesis.
    return {
        FailureState.SHRUNK: b"",
        FailureState.UNSHRUNK: b".secondary",
        FailureState.FIXED: b".fixed",
    }[state]


def _failure_observation_postfix(*, state: FailureState) -> bytes:
    return (
        b"."
        + {
            FailureState.SHRUNK: b"shrunk",
            FailureState.UNSHRUNK: b"unshrunk",
            FailureState.FIXED: b"fixed",
        }[state]
    )


@lru_cache(maxsize=512)
def failure_observation_key(
    key: bytes, choices: Union[HashableIterable[ChoiceT], bytes], state: FailureState
) -> bytes:
    choices_bytes = choices if isinstance(choices, bytes) else choices_to_bytes(choices)
    return (
        key
        + failures_key
        + _failure_observation_postfix(state=state)
        + b"."
        + hashlib.sha1(choices_bytes).digest()
        + b".observation"
    )


class DatabaseEventKey(Enum):
    REPORT = "report"
    CORPUS = "corpus"
    FAILURE_SHRUNK = "failure_shrunk"
    FAILURE_UNSHRUNK = "failure_unshrunk"
    FAILURE_FIXED = "failure_fixed"
    FAILURE_FATAL = "failure_fatal"

    ROLLING_OBSERVATION = "rolling_observation"
    CORPUS_OBSERVATION = "corpus_observation"
    FAILURE_SHRUNK_OBSERVATION = "failure_shrunk_observation"
    FAILURE_UNSHRUNK_OBSERVATION = "failure_unshrunk_observation"
    FAILURE_FIXED_OBSERVATION = "failure_fixed_observation"

    # TODO these two won't ever actually parse, because DatabaseEvent assumes
    # the database_key is the first 48 characters of the key. But workers don't
    # have an associated database key. We will need to refactor event parsing
    # to support database entries without a corresponding test key. We don't
    # rely on this functionality yet, though.
    WORKER_IDENTITY = "worker_identity"
    WORKER_UUID = "worker_uuid"


class DatabaseEntry:
    parse: Callable[[bytes], Any]
    key: DatabaseEventKey

    def __init__(self, database: "HypofuzzDatabase"):
        self.db = database

    @staticmethod
    @abc.abstractmethod
    def matches(full_key: bytes) -> bool:
        pass


class ReportEntry(DatabaseEntry):
    parse: Any = Report.from_json
    key = DatabaseEventKey.REPORT

    @staticmethod
    def matches(full_key: bytes) -> bool:
        return full_key.endswith(reports_key)

    def save(self, key: bytes, report: Report) -> None:
        self.db.save(key + reports_key, _encode(report))

    def delete(self, key: bytes, report: Report) -> None:
        self.db.delete(key + reports_key, _encode(report))

    def fetch(self, key: bytes) -> list[Report]:
        reports = [Report.from_json(v) for v in self.db.fetch(key + reports_key)]
        return [r for r in reports if r is not None]


class RollingObservationEntry(DatabaseEntry):
    key = DatabaseEventKey.ROLLING_OBSERVATION
    parse = Observation.from_json

    @staticmethod
    def matches(full_key: bytes) -> bool:
        return full_key.endswith(rolling_observations_key)

    def __init__(self, database: "HypofuzzDatabase") -> None:
        super().__init__(database)
        # track a per-test observability buffer, so we can discard when we go over
        self._obs_buffers: dict[bytes, deque[Observation]] = defaultdict(deque)

    def save(self, key: bytes, observation: Observation, *, discard_over: int) -> None:
        obs_buffer = self._obs_buffers[key]
        if not obs_buffer:
            # If we don't have anything at all, load from the database - earliest
            # first so we drop those first
            obs_buffer.extend(sorted(self.fetch(key), key=lambda x: x.run_start))

        obs_buffer.append(observation)
        self.db.save(key + rolling_observations_key, _encode(observation))

        # If we have more elements in the buffer than we need, clear them out.
        while len(obs_buffer) > discard_over:
            self.delete(key, obs_buffer.popleft())

    def delete(self, key: bytes, observation: Observation) -> None:
        self.db.delete(key + rolling_observations_key, _encode(observation))

    def fetch(self, key: bytes) -> Iterable[Observation]:
        for value in self.db.fetch(key + rolling_observations_key):
            if observation := Observation.from_json(value):
                yield observation


class CorpusEntry(DatabaseEntry):
    parse = choices_from_bytes  # type: ignore
    key = DatabaseEventKey.CORPUS

    @staticmethod
    def matches(full_key: bytes) -> bool:
        return full_key.endswith(corpus_key)

    def save(self, key: bytes, choices: Iterable[ChoiceT]) -> None:
        self.db.save(key + corpus_key, choices_to_bytes(choices))

    def delete(self, key: bytes, choices: Iterable[ChoiceT]) -> None:
        self.db.delete(key + corpus_key, choices_to_bytes(choices))

    @overload
    def fetch(
        self, key: bytes, *, as_bytes: Literal[False] = False
    ) -> Iterable[ChoicesT]: ...

    @overload
    def fetch(self, key: bytes, *, as_bytes: Literal[True]) -> Iterable[bytes]: ...

    def fetch(
        self, key: bytes, *, as_bytes: bool = False
    ) -> Iterable[Union[ChoicesT, bytes]]:
        for value in self.db.fetch(key + corpus_key):
            if as_bytes:
                yield value
            elif (choices := choices_from_bytes(value)) is not None:
                yield choices


class CorpusObservationEntry(DatabaseEntry):
    key = DatabaseEventKey.CORPUS_OBSERVATION
    parse = Observation.from_json

    @staticmethod
    def matches(full_key: bytes) -> bool:
        return corpus_key in full_key and full_key.endswith(b".observation")

    def save(
        self,
        key: bytes,
        choices: HashableIterable[ChoiceT],
        observation: Observation,
        *,
        delete: bool = True,
    ) -> None:
        _check_observation(observation)
        if not delete:
            self.db.save(corpus_observation_key(key, choices), _encode(observation))
            return

        existing_observations = list(self.fetch_all(key, choices))
        self.db.save(corpus_observation_key(key, choices), _encode(observation))
        for existing in existing_observations:
            self.delete(key, choices, existing)

    def delete(
        self, key: bytes, choices: HashableIterable[ChoiceT], observation: Observation
    ) -> None:
        _check_observation(observation)
        self.db.delete(corpus_observation_key(key, choices), _encode(observation))

    def fetch(
        self,
        key: bytes,
        choices: Union[HashableIterable[ChoiceT], bytes],
    ) -> Optional[Observation]:
        # We expect there to be only a single entry. If there are multiple, we
        # arbitrarily pick one to return.
        try:
            return next(iter(self.fetch_all(key, choices)))
        except StopIteration:
            return None

    def fetch_all(
        self,
        key: bytes,
        choices: Union[HashableIterable[ChoiceT], bytes],
    ) -> Iterable[Observation]:
        for value in self.db.fetch(corpus_observation_key(key, choices)):
            if observation := Observation.from_json(value):
                yield observation


class FailureEntry(DatabaseEntry):
    state: FailureState
    parse = choices_from_bytes  # type: ignore

    @classmethod
    def matches(cls, full_key: bytes) -> bool:
        database_key = full_key[: DatabaseEvent.DATABASE_KEY_LENGTH]
        return full_key == database_key + _failure_postfix(state=cls.state)

    @staticmethod
    def _key(key: bytes, *, state: FailureState) -> bytes:
        return key + _failure_postfix(state=state)

    def save(
        self,
        key: bytes,
        choices: ChoicesT,
        observation: Optional[Observation],
    ) -> None:
        self.db.save(self._key(key, state=self.state), choices_to_bytes(choices))

        if observation is not None:
            _check_observation(observation)
            existing_observations = list(
                self.db.failure_observations(state=self.state).fetch_all(key, choices)
            )
            self.db.failure_observations(state=self.state).save(
                key, choices, observation
            )
            for existing in existing_observations:
                _check_observation(existing)
                self.db.failure_observations(state=self.state).delete(
                    key, choices, existing
                )

    def delete(
        self,
        key: bytes,
        choices: ChoicesT,
    ) -> None:
        self.db.delete(self._key(key, state=self.state), choices_to_bytes(choices))
        for observation in list(
            self.db.failure_observations(state=self.state).fetch_all(key, choices)
        ):
            _check_observation(observation)
            self.db.failure_observations(state=self.state).delete(
                key, choices, observation
            )

    def fetch(self, key: bytes) -> Iterable[ChoicesT]:
        for value in self.db.fetch(self._key(key, state=self.state)):
            if (choices := choices_from_bytes(value)) is not None:
                yield choices


class FailureFixedEntry(FailureEntry):
    state = FailureState.FIXED
    key = DatabaseEventKey.FAILURE_FIXED


class FailureShrunkEntry(FailureEntry):
    state = FailureState.SHRUNK
    key = DatabaseEventKey.FAILURE_SHRUNK


class FailureUnshrunkEntry(FailureEntry):
    state = FailureState.UNSHRUNK
    key = DatabaseEventKey.FAILURE_UNSHRUNK


class FailureObservationEntry(DatabaseEntry):
    parse = Observation.from_json
    state: FailureState

    @classmethod
    def matches(cls, full_key: bytes) -> bool:
        return (
            failures_key + _failure_observation_postfix(state=cls.state)
        ) in full_key and full_key.endswith(b".observation")

    def save(self, key: bytes, choices: ChoicesT, observation: Observation) -> None:
        self.db.save(
            failure_observation_key(key, choices, state=self.state),
            _encode(observation),
        )

    def delete(self, key: bytes, choices: ChoicesT, observation: Observation) -> None:
        self.db.delete(
            failure_observation_key(key, choices, state=self.state),
            _encode(observation),
        )

    def fetch(self, key: bytes, choices: ChoicesT) -> Optional[Observation]:
        try:
            return next(iter(self.fetch_all(key, choices)))
        except StopIteration:
            return None

    def fetch_all(self, key: bytes, choices: ChoicesT) -> Iterable[Observation]:
        for value in self.db.fetch(
            failure_observation_key(key, choices, state=self.state)
        ):
            if observation := Observation.from_json(value):
                yield observation


class FailureObservationFixedEntry(FailureObservationEntry):
    state = FailureState.FIXED
    key = DatabaseEventKey.FAILURE_FIXED_OBSERVATION


class FailureObservationShrunkEntry(FailureObservationEntry):
    state = FailureState.SHRUNK
    key = DatabaseEventKey.FAILURE_SHRUNK_OBSERVATION


class FailureObservationUnshrunkEntry(FailureObservationEntry):
    state = FailureState.UNSHRUNK
    key = DatabaseEventKey.FAILURE_UNSHRUNK_OBSERVATION


class FatalFailureEntry(DatabaseEntry):
    parse: Any = FatalFailure.from_json
    key = DatabaseEventKey.FAILURE_FATAL

    @staticmethod
    def matches(full_key: bytes) -> bool:
        return full_key.endswith(fatal_failure_key)

    def save(self, key: bytes, failure: FatalFailure) -> None:
        # we don't want to accumulate multiple fatal failures, so replace any
        # existing ones with the new one.
        self.delete(key)
        self.db.save(key + fatal_failure_key, _encode(failure))

    def delete(self, key: bytes) -> None:
        for failure in self.fetch_all(key):
            self.db.delete(key + fatal_failure_key, _encode(failure))

    def fetch_all(self, key: bytes) -> Iterable[FatalFailure]:
        for value in self.db.fetch(key + fatal_failure_key):
            if failure := FatalFailure.from_json(value):
                yield failure

    def fetch(self, key: bytes) -> Optional[FatalFailure]:
        try:
            return next(iter(self.fetch_all(key)))
        except StopIteration:
            return None


class WorkerIdentityEntry(DatabaseEntry):
    parse: Any = WorkerIdentity.from_json
    key = DatabaseEventKey.WORKER_IDENTITY

    @staticmethod
    def matches(full_key: bytes) -> bool:
        return full_key.startswith(worker_identity_key)

    @staticmethod
    def _key(uuid: bytes) -> bytes:
        return worker_identity_key + b"." + uuid

    def save(self, worker_identity: WorkerIdentity) -> None:
        uuid = worker_identity.uuid.encode("ascii")
        self.delete(uuid)
        self.db.save(self._key(uuid), _encode(worker_identity))

    def delete(self, uuid: bytes) -> None:
        for worker_identity in self.fetch_all(uuid):
            self.db.delete(self._key(uuid), _encode(worker_identity))

    def fetch(self, uuid: bytes) -> Optional[WorkerIdentity]:
        try:
            return next(iter(self.fetch_all(uuid)))
        except StopIteration:
            return None

    def fetch_all(self, uuid: bytes) -> Iterable[WorkerIdentity]:
        for value in self.db.fetch(self._key(uuid)):
            if worker_identity := WorkerIdentity.from_json(value):
                yield worker_identity


class WorkerUUIDEntry(DatabaseEntry):
    parse: Any = lambda x: x
    key = DatabaseEventKey.WORKER_UUID

    @staticmethod
    def matches(full_key: bytes) -> bool:
        return full_key == worker_uuids_key

    def fetch(self) -> Iterable[bytes]:
        yield from self.db.fetch(worker_uuids_key)

    def save(self, uuid: bytes) -> None:
        self.db.save(worker_uuids_key, uuid)

    def delete(self, uuid: bytes) -> None:
        self.db.delete(worker_uuids_key, uuid)


ALL_ENTRIES: list[type[DatabaseEntry]] = [
    ReportEntry,
    RollingObservationEntry,
    CorpusEntry,
    CorpusObservationEntry,
    FailureFixedEntry,
    FailureShrunkEntry,
    FailureUnshrunkEntry,
    FailureObservationFixedEntry,
    FailureObservationShrunkEntry,
    FailureObservationUnshrunkEntry,
    FatalFailureEntry,
    WorkerIdentityEntry,
]


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
        full_key: Any
        value: Any
        (event_type, (full_key, value)) = event
        # unfortunately a key which is exactly equal to the database key length
        # is valid, and we can't adjust that, because that's the database key
        # hypothesis uses for failures.
        if len(full_key) < cls.DATABASE_KEY_LENGTH or (
            len(full_key) > cls.DATABASE_KEY_LENGTH
            # ord because indexing into bytes converts to int
            and full_key[cls.DATABASE_KEY_LENGTH] != ord(".")
        ):
            return None

        database_key = full_key[: cls.DATABASE_KEY_LENGTH]

        matched_entry = None
        for entry in ALL_ENTRIES:
            if entry.matches(full_key):
                matched_entry = entry
                break

        if matched_entry is None:
            return None

        if event_type == "save":
            assert value is not None

        # value might be None for event_type == "delete"
        if value is not None:
            value = matched_entry.parse(value)
            if value is None:
                # invalid parse
                return None

        return DatabaseEvent(
            type=event_type,
            database_key=database_key,
            key=matched_entry.key,
            value=value,
        )


class HypofuzzDatabase:
    def __init__(self, db: ExampleDatabase) -> None:
        self._db = db
        self.reports = ReportEntry(self)
        self.rolling_observations = RollingObservationEntry(self)
        self.corpus = CorpusEntry(self)
        self.corpus_observations = CorpusObservationEntry(self)
        self.fatal_failures = FatalFailureEntry(self)
        self.worker_identities = WorkerIdentityEntry(self)
        self.worker_uuids = WorkerUUIDEntry(self)

        # access via .failures(state=...) and .failure_observations(state=...)
        # instead
        self._failures_fixed = FailureFixedEntry(self)
        self._failures_shrunk = FailureShrunkEntry(self)
        self._failures_unshrunk = FailureUnshrunkEntry(self)
        self._failure_observations_fixed = FailureObservationFixedEntry(self)
        self._failure_observations_shrunk = FailureObservationShrunkEntry(self)
        self._failure_observations_unshrunk = FailureObservationUnshrunkEntry(self)

    def __str__(self) -> str:
        return f"HypofuzzDatabase({self._db!r})"

    __repr__ = __str__

    def save(self, key: bytes, value: bytes) -> None:
        self._db.save(key, value)

    def fetch(self, key: bytes) -> Iterable[bytes]:
        yield from self._db.fetch(key)

    def delete(self, key: bytes, value: bytes) -> None:
        self._db.delete(key, value)

    def failures(self, *, state: FailureState) -> FailureEntry:
        if state == FailureState.FIXED:
            return self._failures_fixed
        elif state == FailureState.SHRUNK:
            return self._failures_shrunk
        elif state == FailureState.UNSHRUNK:
            return self._failures_unshrunk
        else:
            raise ValueError(f"Invalid failure state: {state}")

    def failure_observations(self, *, state: FailureState) -> FailureObservationEntry:
        if state == FailureState.FIXED:
            return self._failure_observations_fixed
        elif state == FailureState.SHRUNK:
            return self._failure_observations_shrunk
        elif state == FailureState.UNSHRUNK:
            return self._failure_observations_unshrunk
        else:
            raise ValueError(f"Invalid failure state: {state}")
