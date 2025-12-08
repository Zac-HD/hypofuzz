import math
from dataclasses import dataclass, field
from itertools import pairwise
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
    def _assert_reports_ordered(
        reports: list[ReportWithDiff], attributes: list[str]
    ) -> None:
        for attribute in attributes:
            assert all(
                getattr(r1, attribute) <= getattr(r2, attribute)
                for r1, r2 in pairwise(reports)
            ), (attribute, [getattr(r, attribute) for r in reports])

    def _linear_sort_key(self, r: ReportWithDiff) -> tuple[float, str]:
        return (r.timestamp_monotonic, r.worker_uuid)

    def _check_invariants(self) -> None:
        # this function is pretty expensive. Only call it at important junctures,
        # or in tests
        assert all(
            self._linear_sort_key(r1) <= self._linear_sort_key(r2)
            for r1, r2 in pairwise(self.linear_reports)
        ), [self._linear_sort_key(r) for r in self.linear_reports]

        linear_status_counts = self.linear_status_counts()
        assert all(
            v1 <= v2 for v1, v2 in pairwise(linear_status_counts)
        ), linear_status_counts

        linear_elapsed_time = self.linear_elapsed_time()
        assert all(
            v1 <= v2 for v1, v2 in pairwise(linear_elapsed_time)
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
            self._assert_reports_ordered(self.linear_reports, ["timestamp_monotonic"])

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
            # we expect reports to *usually* arrive in-order. If a report does
            # arrive in order, then we have last_worker_report = reports[-1].
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
        if linear_report.phase is not Phase.REPLAY or (
            linear_report.behaviors >= self.behaviors
            and linear_report.fingerprints >= self.fingerprints
        ):
            # insert in-order, maintaining the sorted invariant
            index = fast_bisect_right(
                self.linear_reports,
                self._linear_sort_key(linear_report),
                key=self._linear_sort_key,
            )
            self.linear_reports.insert(index, linear_report)

            # If we inserted not at the end of linear_reports, invalidate the cumsum
            # caches. The cache extension logic assumes reports are appended at the
            # end, so inserting in the middle would cause incorrect cumsum values.
            if index != len(self.linear_reports) - 1:
                self._status_counts_cumsum = LRUCache(16)
                self._elapsed_time_cumsum = LRUCache(16)

            # If we inserted not at the end of the worker's reports (by elapsed_time),
            # we need to recompute the diffs for all subsequent reports from this worker.
            # We check reports_by_worker, not linear_reports, because the worker's
            # reports might have the same sort key in linear_reports but different
            # elapsed_times.
            worker_reports = self.reports_by_worker[report.worker_uuid]
            if reports_index + 1 < len(worker_reports):
                last_report = linear_report
                for j in range(reports_index + 1, len(worker_reports)):
                    old_report = worker_reports[j]
                    new_report = ReportWithDiff.from_reports(
                        old_report,
                        last_worker_report=last_report,
                    )

                    # Update in reports_by_worker
                    worker_reports[j] = new_report

                    # Update in linear_reports (if it exists there - REPLAY reports
                    # might not be in linear_reports). We must remove and re-insert
                    # rather than updating in place, because the sort key may have
                    # changed.
                    for i, lr in enumerate(self.linear_reports):
                        if lr is old_report:
                            self.linear_reports.pop(i)
                            new_index = fast_bisect_right(
                                self.linear_reports,
                                self._linear_sort_key(new_report),
                                key=self._linear_sort_key,
                            )
                            self.linear_reports.insert(new_index, new_report)
                            break

                    last_report = new_report

                # Invalidate the cumsum caches. When reports are inserted out of
                # order and moved around, the positions shift in complex ways, so
                # we clear the entire cache rather than trying to partially invalidate.
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

        return count_stable / (count_stable + count_unstable)

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
