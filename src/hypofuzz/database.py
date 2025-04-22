import dataclasses
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, is_dataclass
from enum import Enum
from functools import cache
from typing import Any, Optional

from hypothesis import settings
from hypothesis.database import BackgroundWriteDatabase, ExampleDatabase
from hypothesis.internal.conjecture.data import Status
from sortedcontainers import SortedList


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
    def from_dict(data: dict) -> "WorkerIdentity":
        return WorkerIdentity(**data)


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


# Conceptually:
# * A report is an incremental progress marker which we don't want to delete,
#   because seeing intermediary stages in e.g. a graph is useful information
# * Metadata is the latest status of a test, which we might update to something
#   different if new information comes along. Intermediate metadata steps are
#   not saved because they are not interesting.
@dataclass(frozen=True)
class Report:
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
    def from_dict(data: dict) -> "Report":
        data = dict(data)
        data["worker"] = WorkerIdentity.from_dict(data["worker"])
        data["status_counts"] = StatusCounts(
            {Status(int(k)): v for k, v in data["status_counts"].items()}
        )
        data["phase"] = Phase(data["phase"])
        return Report(**data)

    def __sub__(self, other):
        if other is not None and not isinstance(other, type(self)):
            return NotImplemented
        if other is None:
            return ReportWithDiff(
                **dataclasses.asdict(self),
                elapsed_time_diff=self.elapsed_time,
                status_counts_diff=self.status_counts,
            )
        assert other.elapsed_time <= self.elapsed_time
        assert other.status_counts <= self.status_counts
        return ReportWithDiff(
            **dataclasses.asdict(self),
            elapsed_time_diff=self.elapsed_time - other.elapsed_time,
            status_counts_diff=self.status_counts - other.status_counts,
        )


@dataclass
class ReportWithDiff(Report):
    elapsed_time_diff: float
    status_counts_diff: StatusCounts


@dataclass(frozen=True)
class Metadata:
    nodeid: str
    seed_pool: list[list[str]]
    failures: list[list[str]]

    @staticmethod
    def from_dict(data: dict) -> "Metadata":
        data = dict(data)
        return Metadata(**data)


reports_key = b".hypofuzz.reports"
metadata_key = b".hypofuzz.metadata"


class HypofuzzDatabase:
    def __init__(self, db: ExampleDatabase) -> None:
        self._db = db

    def __str__(self) -> str:
        return f"HypofuzzDatabase({self._db!r})"

    __repr__ = __str__

    def _encode(self, data: Any) -> bytes:
        return bytes(json.dumps(data, cls=HypofuzzEncoder), "ascii")

    def save(self, key: bytes, value: bytes) -> None:
        self._db.save(key, value)

    def fetch(self, key: bytes) -> Iterable[bytes]:
        return self._db.fetch(key)

    def delete(self, key: bytes, value: bytes) -> None:
        self._db.delete(key, value)

    def save_report(self, key: bytes, report: Report) -> None:
        self.save(key + reports_key, self._encode(report))

    def delete_report(self, key: bytes, report: Report) -> None:
        self.delete(key + reports_key, self._encode(report))

    def fetch_reports(self, key: bytes) -> list[Report]:
        return [Report.from_dict(json.loads(v)) for v in self.fetch(key + reports_key)]

    def fetch_metadata(self, key: bytes) -> list[Metadata]:
        return [
            Metadata.from_dict(json.loads(v)) for v in self.fetch(key + metadata_key)
        ]

    def replace_metadata(self, key: bytes, metadata: Metadata) -> None:
        # save and then delete to avoid intermediary state where no metadata is
        # in the db. > 1 metadata is better than 0
        old_metadatas = list(self.fetch_metadata(key))

        self.save(key + metadata_key, self._encode(metadata))
        for old_metadata in old_metadatas:
            if old_metadata == metadata:
                # don't remove something equal to the thing we just saved. This
                # would cause us to reset to zero entries.
                continue
            self.delete(key + metadata_key, self._encode(old_metadata))


# cache to make the db a singleton. We defer creation until first-usage to ensure
# that we use the test-time database setting, rather than init-time.
@cache
def get_db() -> HypofuzzDatabase:
    db = settings().database
    if isinstance(db, BackgroundWriteDatabase):
        return HypofuzzDatabase(db)
    return HypofuzzDatabase(BackgroundWriteDatabase(db))


def linearize_reports(reports: list[Report]) -> dict[str, list[ReportWithDiff]]:
    """
    Given an (arbitrarily ordered) list of reports, potentially from different
    workers and potentially with overlapping durations, reconstruct a best-effort
    linearization suitable for e.g. display in the dashboard.
    """
    # Start by grouping reports by (db_key, worker_uuid).
    grouped: defaultdict[tuple[str, str], SortedList[Report]] = defaultdict(
        lambda: SortedList(lambda r: r.timestamp)
    )
    for r in reports:
        grouped[(r.nodeid, r.worker.uuid)].add(r)

    # For each test for each worker, we can assume that elapsed time, timestamp,
    # and number of inputs are monotonically increasing.  We can therefore scan
    # through each of these, creating ReportWithDiff instances and adding those
    # to the list for that nodeid (which is sorted by timestamp).
    diffed = defaultdict(lambda: SortedList(lambda r: r.timestamp))
    for (nodeid, _), these_reports in grouped.items():
        prev = None
        for r in these_reports:
            diffed[nodeid].add(r - prev)
            prev = r

    # For display, the frontend should:
    #   - do a cuumulative sum over the *_diff attributes to get the x-axis
    #   - skip over replay-phase reports after the first non-replay report.
    return {k: list(v) for k, v in diffed.items()}
