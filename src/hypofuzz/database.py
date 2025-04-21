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
        # compatibility with older dbs
        if "note" in data:
            del data["note"]
        data["worker"] = WorkerIdentity.from_dict(data["worker"])
        data["status_counts"] = StatusCounts(
            {Status(int(k)): v for k, v in data["status_counts"].items()}
        )
        data["phase"] = Phase(data["phase"])
        return Report(**data)


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


@dataclass
class Offsets:
    status_counts: dict[str, StatusCounts]
    elapsed_time: dict[str, float]


@dataclass
class LinearReports:
    reports: list[Report]
    offsets: Offsets


def linearize_reports(reports: list[Report]) -> LinearReports:
    """
    Given an (arbitrarily ordered) list of reports, potentially from different
    workers and potentially with overlapping durations, reconstruct a best-effort
    linearization suitable for e.g. display in the dashboard.
    """
    # The linearization algorithm is as follows:
    # * Track the total number of inputs and the total elapsed time of the
    #   current linearized history.
    # * Examine reports in sorted timestamp order. Compute the new ninputs n and new
    #   elapsed_time t relative to the previous report from that worker.
    # * Append a new report to the linearized history, which is the same as the
    #   actual report but with inputs linearized_n + n and elapsed time
    #   linearized_elapsed_time + t.
    #
    # We could improve lineariztion for time periods with overlapping workers by
    # taking the maximum of any coverage achieved in that interval, if all the
    # workers are fuzzing the same code state. If the workers have different code
    # states (e.g. a different git hash), then we have no choice but to treat
    # the reported coverage as canonical and accept coverage jitter in the graph.

    total_statuses = StatusCounts(dict.fromkeys(Status, 0))
    total_elapsed_time = 0.0
    linearized_reports = []
    # we track a running total of ninputs and elapsed_time for each worker. This
    # lets us compute new ninputs and elapsed_time for each report, relative to
    # the previous report.
    #
    # We could equivalently store ninputs_new and elapsed_time_new on the reports.
    # (but then deletion or loss of arbitrary reports becomes unsound without fixing
    # up the subsequent report).
    offsets_statuses: dict[str, StatusCounts] = defaultdict(
        lambda: StatusCounts(dict.fromkeys(Status, 0))
    )
    offsets_elapsed_time: dict[str, float] = defaultdict(float)
    # We sort by timestamp, and rely on the invariant that reports from an
    # individual worker always monotonically increase in both ninputs and elapsed_time
    # as the timestamp increases, so that sorting by timestamp is enough to sort by
    # all three attributes (within an individual worker).
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
        # still cpu time you're paying for.
        total_statuses += statuses_diff
        total_elapsed_time += elapsed_time_diff
        offsets_statuses[report.worker.uuid] = report.status_counts
        offsets_elapsed_time[report.worker.uuid] = report.elapsed_time

    return LinearReports(
        reports=linearized_reports,
        offsets=Offsets(
            status_counts=offsets_statuses,
            elapsed_time=offsets_elapsed_time,
        ),
    )
