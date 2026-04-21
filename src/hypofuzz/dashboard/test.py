import math
from dataclasses import dataclass, field
from typing import TypeVar

from hypothesis.internal.cache import LRUCache

from hypofuzz.compat import bisect_right
from hypofuzz.database import (
    FailureState,
    FatalFailure,
    Observation,
    Phase,
    Report,
    ReportWithDiff,
    Stability,
    StatusCounts,
    convert_db_key,
)
from hypofuzz.utils import fast_bisect_right, k_way_merge

T = TypeVar("T")


@dataclass
class Test:
    database_key: str
    nodeid: str
    rolling_observations: list[Observation]
    corpus_observations: list[Observation]
    failures: dict[str, tuple[FailureState, Observation]]
    fatal_failure: FatalFailure | None
    reports_by_worker: dict[str, list[ReportWithDiff]]

    linear_reports: list[ReportWithDiff] = field(init=False)

    # prevent pytest from trying to collect this class as a test
    __test__ = False

    # TODO: turn into a regular class and add reports= and reports_by_workers
    # as alternative constructors? reports_by_workers is only to match the dashboard
    # class, we don't actually instantiate Test like that anywhere in python
    def __post_init__(self) -> None:
        self.linear_reports = []
        # map of since: float to (start_idx, list[StatusCounts])
        self._status_counts_cumsum: LRUCache[float, tuple[int, list[StatusCounts]]] = (
            LRUCache(16)
        )
        self._elapsed_time_cumsum: LRUCache[float, tuple[int, list[float]]] = LRUCache(
            16
        )

        reports_by_worker = self.reports_by_worker
        self.reports_by_worker = {}

        # use k-way merge for nlog(k) performance, since reports_by_worker
        # is already sorted.
        #
        # This sorting doesn't matter for correctness, but it does for performance,
        # by minimizing the amount of work each bisect_right call does when
        # inserting into reports_by_worker. (I have not profiled this).
        for report in k_way_merge(
            list(reports_by_worker.values()), key=lambda r: r.elapsed_time
        ):
            self.add_report(report)

        self._check_invariants()

    @property
    def database_key_bytes(self) -> bytes:
        return convert_db_key(self.database_key, to="bytes")

    @staticmethod
    def _linear_sort_key(r: ReportWithDiff) -> tuple[float, str]:
        # Ordering linear_reports solely by timestamp_monotonic is not a total
        # order: two reports from different workers can easily collide. Without
        # a tiebreaker the position of such reports depended on insertion order,
        # which made add_report non-commutative and allowed the linearization to
        # desync from itself after out-of-order inserts.
        return (r.timestamp_monotonic, r.worker_uuid)

    @staticmethod
    def _assert_reports_ordered(
        reports: list[ReportWithDiff], attributes: list[str]
    ) -> None:
        for attribute in attributes:
            assert all(
                getattr(r1, attribute) <= getattr(r2, attribute)
                for r1, r2 in zip(reports, reports[1:])
            ), (attribute, [getattr(r, attribute) for r in reports])

    def _check_invariants(self) -> None:
        # this function is pretty expensive. Only call it at important junctures,
        # or in tests
        linear_keys = [self._linear_sort_key(r) for r in self.linear_reports]
        assert all(k1 <= k2 for k1, k2 in zip(linear_keys, linear_keys[1:])), (
            linear_keys
        )

        linear_status_counts = self.linear_status_counts()
        assert all(
            v1 <= v2 for v1, v2 in zip(linear_status_counts, linear_status_counts[1:])
        ), linear_status_counts

        linear_elapsed_time = self.linear_elapsed_time()
        assert all(
            v1 <= v2 for v1, v2 in zip(linear_elapsed_time, linear_elapsed_time[1:])
        ), linear_elapsed_time
        assert (
            len(linear_elapsed_time)
            == len(linear_status_counts)
            == len(self.linear_reports)
        )

        for worker_uuid, reports in self.reports_by_worker.items():
            assert {r.nodeid for r in reports} == {self.nodeid}, (
                self.nodeid,
                {r.nodeid for r in reports},
            )
            assert {r.database_key for r in reports} == {self.database_key}, (
                self.database_key,
                {r.database_key for r in reports},
            )
            assert {r.worker_uuid for r in reports} == {worker_uuid}
            # within a single worker, reports are sorted by elapsed_time
            self._assert_reports_ordered(reports, ["elapsed_time", "status_counts"])

        # this is not always true due to floating point error accumulation.
        # total_elapsed_time = 0.0
        # for reports in self.reports_by_worker.values():
        #     total_elapsed_time += reports[-1].elapsed_time
        # assert self.elapsed_time == total_elapsed_time

    def add_report(self, report: Report) -> None:
        last_worker_report = None
        reports_index = 0
        if report.worker_uuid in self.reports_by_worker:
            reports = self.reports_by_worker[report.worker_uuid]
            # If a report is added out of order, then the appropriate report to
            # compute the diff against is the one right before the new report.
            # Any guaranteed-monotonic attribute will work here (either
            # elapsed_time or status_counts). Use elapsed_time.
            #
            # we expect reports to *usually* arrive in-order, which case the
            # appropriate report to diff against is reports[-1].
            reports_index = fast_bisect_right(
                reports, report.elapsed_time, key=lambda r: r.elapsed_time
            )
            last_worker_report = (
                reports[reports_index - 1] if reports_index != 0 else None
            )

        linear_report = ReportWithDiff.from_reports(
            report, last_worker_report=last_worker_report
        )
        # support the by-worker access pattern, for consumers of Test. we use this
        # when sending over the websocket, to compress the worker information into
        # a single message for all its reports.
        self.reports_by_worker.setdefault(report.worker_uuid, []).insert(
            reports_index, linear_report
        )

        # we include Phase.REPLAY reports in the linearization iff it does not
        # decrease the number of behaviors or fingerprints.
        # this lets us nicely show workers that were not the first worker, or
        # even the linearized version of concurrent workers that were not the first worker.

        # Phase.REPLAY does not count towards:
        #   * status_counts
        #   * elapsed_time
        #   * reports
        #   * behaviors
        #   * fingerprints
        #   * phase (should we change this? would cause status flipflop with multiple workers)
        # nor is it displayed on dashboard graphs.
        # This is fine for display purposes, since these statistics are intended
        # to convey the time spent searching for bugs. But we should be careful
        # when measuring cost to compute a separate "overhead" statistic which
        # takes every input and elapsed_time into account regardless of phase.
        included_in_linear = linear_report.phase is not Phase.REPLAY or (
            linear_report.behaviors >= self.behaviors
            and linear_report.fingerprints >= self.fingerprints
        )
        if included_in_linear:
            # insert in-order, maintaining the sorted invariant
            index = fast_bisect_right(
                self.linear_reports,
                self._linear_sort_key(linear_report),
                key=self._linear_sort_key,
            )
            self.linear_reports.insert(index, linear_report)
            appended_at_end = index == len(self.linear_reports) - 1
        else:
            appended_at_end = False

        # If this report is not the last one for its worker, the subsequent
        # reports' diffs were computed against the wrong predecessor. Recompute
        # them in order, updating both reports_by_worker and linear_reports.
        #
        # We iterate reports_by_worker (sorted by elapsed_time) rather than
        # linear_reports (sorted by timestamp_monotonic); the two orderings can
        # diverge, and elapsed_time is what ReportWithDiff.from_reports uses
        # to compute diffs.
        worker_reports = self.reports_by_worker[report.worker_uuid]
        any_recomputed = reports_index + 1 < len(worker_reports)
        predecessor = linear_report
        for j in range(reports_index + 1, len(worker_reports)):
            stale = worker_reports[j]
            fresh = ReportWithDiff.from_reports(
                stale, last_worker_report=predecessor
            )
            worker_reports[j] = fresh

            # timestamp_monotonic can only have increased, so the report may
            # need to move later in linear_reports. Pop-and-reinsert rather
            # than updating in place to preserve the sort invariant. Some
            # reports (filtered-out REPLAYs) are not in linear_reports, so
            # skip those silently.
            for i, lr in enumerate(self.linear_reports):
                if lr is stale:
                    del self.linear_reports[i]
                    new_index = fast_bisect_right(
                        self.linear_reports,
                        self._linear_sort_key(fresh),
                        key=self._linear_sort_key,
                    )
                    self.linear_reports.insert(new_index, fresh)
                    break
            predecessor = fresh

        # The cumsum caches assume linear_reports only grows at the end. Any
        # middle insert or recompute of existing reports invalidates them.
        if not appended_at_end or any_recomputed:
            self._status_counts_cumsum = LRUCache(16)
            self._elapsed_time_cumsum = LRUCache(16)

    @property
    def stability(self) -> float | None:
        if not self.rolling_observations:
            return None

        # not that we do not compute stability as
        # count_stable / len(self.rolling_observations), because we want to avoid
        # counting observations with unknown stability against the overall stability.
        count_stable = sum(
            observation.stability is Stability.STABLE
            for observation in self.rolling_observations
        )
        count_unstable = sum(
            observation.stability is Stability.UNSTABLE
            for observation in self.rolling_observations
        )

        # Every observation has UNKNOWN stability (the remaining Stability
        # variant), so there is no signal to compute a ratio from. Returning
        # a 0/0 ZeroDivisionError here used to tear down the dashboard
        # websocket every time the UI polled (#245).
        total = count_stable + count_unstable
        if total == 0:
            return None

        return count_stable / total

    @property
    def phase(self) -> Phase | None:
        return self.linear_reports[-1].phase if self.linear_reports else None

    @property
    def behaviors(self) -> int:
        return self.linear_reports[-1].behaviors if self.linear_reports else 0

    @property
    def fingerprints(self) -> int:
        return self.linear_reports[-1].fingerprints if self.linear_reports else 0

    def ninputs(self, since: float = -math.inf) -> int:
        return sum(self.linear_status_counts(since=since)[-1].values())

    def _cumsum(
        self,
        *,
        cache: LRUCache,
        attr: str,
        since: float = -math.inf,
        initial: T,
    ) -> list[T]:
        cumsum: list[T]
        if since in cache:
            (start_idx, cumsum) = cache[since]
            if len(cumsum) < len(self.linear_reports[start_idx:]):
                # extend cumsum with any new reports
                running = cumsum[-1] if cumsum else initial
                for report in self.linear_reports[start_idx + len(cumsum) :]:
                    value = getattr(report, attr)
                    assert value >= initial
                    running += value
                    cumsum.append(running)
                cache[since] = (start_idx, cumsum)

            return cumsum

        cumsum = []
        start_idx = bisect_right(
            self.linear_reports, since, key=lambda r: r.timestamp_monotonic
        )
        running = initial
        for report in self.linear_reports[start_idx:]:
            value = getattr(report, attr)
            assert value >= initial
            running += value
            cumsum.append(running)
        cache[since] = (start_idx, cumsum)
        return cumsum

    def linear_status_counts(self, *, since: float = -math.inf) -> list[StatusCounts]:
        return self._cumsum(
            cache=self._status_counts_cumsum,
            attr="status_counts_diff",
            since=since,
            initial=StatusCounts(),
        )

    def linear_elapsed_time(self, *, since: float = -math.inf) -> list[float]:
        return self._cumsum(
            cache=self._elapsed_time_cumsum,
            attr="elapsed_time_diff",
            since=since,
            initial=0.0,
        )
