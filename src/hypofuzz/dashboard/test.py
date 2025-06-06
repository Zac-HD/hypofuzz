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
    failure: Optional[Observation]
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
                for r1, r2 in zip(reports, reports[1:])
            ), (attribute, [getattr(r, attribute) for r in reports])

    def _check_invariants(self) -> None:
        # this function is pretty expensive, only call at important junctures
        # or during test-time
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
            # insert in-order, maintaining the sorted invariant
            index = fast_bisect_right(
                self.linear_reports,
                linear_report.timestamp_monotonic,
                key=lambda r: r.timestamp_monotonic,
            )
            self.linear_reports.insert(index, linear_report)
            if index != len(self.linear_reports) - 1:
                # if we didn't just append this report to the end, we need to:
                # * recompute the diff for the next report from this worker (if
                #   there is one)
                # * invalidate cumsum caches for the indices after `index`
                next_worker_report = None
                for i_offset, report_candidate in enumerate(
                    self.linear_reports[index + 1 :]
                ):
                    if linear_report.worker_uuid == report_candidate.worker_uuid:
                        next_worker_report = report_candidate
                        break

                # note that there need not be another report from this worker
                # after this report, if this was the first report to arrive from
                # the worker, and it arrived out of order wrt timestamp_monotonic
                # for the existing linear_reports.
                if next_worker_report is not None:
                    assert (
                        self.linear_reports[index + 1 + i_offset] == next_worker_report
                    )
                    next_worker_report = ReportWithDiff.from_reports(
                        next_worker_report,
                        last_worker_report=linear_report,
                    )
                    self.linear_reports[index + 1 + i_offset] = next_worker_report

                # now invalidate the cumsum caches for any indices after `index`
                caches: list[LRUCache] = [
                    self._status_counts_cumsum,
                    self._elapsed_time_cumsum,
                ]
                for cache in caches:
                    for key, (start_idx, values) in cache.cache.items():
                        if index >= start_idx:
                            cache[key] = (start_idx, values[: index - start_idx])

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
