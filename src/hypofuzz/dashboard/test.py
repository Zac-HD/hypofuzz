import itertools
import math
from dataclasses import dataclass, field
from typing import Optional, TypeVar

from hypothesis.internal.cache import LRUCache

from hypofuzz.compat import bisect_right
from hypofuzz.database import (
    Observation,
    Phase,
    Report,
    ReportWithDiff,
    StatusCounts,
)

T = TypeVar("T")


@dataclass
class Test:
    database_key: str
    nodeid: str
    rolling_observations: list[Observation]
    corpus_observations: list[Observation]
    failure: Optional[Observation]
    reports_by_worker: dict[str, list[Report]]

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

        # TODO: use k-way merge for nlog(k)) performance, since reports_by_worker
        # is already sorted.
        # This sorting won't matter for correctness (once we correctly insert
        # out-of-order reports), but it will for performance, by minimizing the
        # number of .bisect calls in the worker reports list.
        for report in sorted(
            itertools.chain.from_iterable(reports_by_worker.values()),
            key=lambda r: r.elapsed_time,
        ):
            self.add_report(report)

        self._check_invariants()

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
        # this entire function is pretty expensive, move from run-time to test-time
        # once we're more confident
        self._assert_reports_ordered(self.linear_reports, ["timestamp_monotonic"])

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
            assert {r.nodeid for r in reports} == {self.nodeid}
            assert {r.database_key for r in reports} == {self.database_key}
            assert {r.worker_uuid for r in reports} == {worker_uuid}
            self._assert_reports_ordered(self.linear_reports, ["timestamp_monotonic"])

        # this is not always true due to floating point error accumulation.
        # total_elapsed_time = 0.0
        # for reports in self.reports_by_worker.values():
        #     total_elapsed_time += reports[-1].elapsed_time
        # assert self.elapsed_time == total_elapsed_time

    def add_report(self, report: Report) -> None:
        # we use last_report to compute timestamp_monotonic, and last_report_worker
        # to compute status_count_diff and elapsed_time_diff
        last_report = self.linear_reports[-1] if self.linear_reports else None
        last_worker_report = (
            None
            if report.worker_uuid not in self.reports_by_worker
            else self.reports_by_worker[report.worker_uuid][-1]
        )
        if (
            last_worker_report is not None
            and last_worker_report.elapsed_time > report.elapsed_time
        ):
            # If last_report.elapsed_time > report.elapsed_time, the reports have arrived
            # out of order. we've already accounted for the diff of `report`; last_report
            # essentially became the combined report of report + last_report.
            #
            # TODO instead of dropping this report, insert it into the lists at
            # the appropriate index, and recompute the diff for the next
            # report. That way the e.g. dashboard graph still gets the report.
            return

        linear_report = ReportWithDiff.from_reports(
            report, last_report=last_report, last_worker_report=last_worker_report
        )
        # support the by-worker access pattern. We only access index [-1] though
        # - should we store self.last_reports_by_worker instead?
        self.reports_by_worker.setdefault(report.worker_uuid, []).append(linear_report)
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
        if linear_report.phase is not Phase.REPLAY:
            self.linear_reports.append(linear_report)

    @property
    def phase(self) -> Optional[Phase]:
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
