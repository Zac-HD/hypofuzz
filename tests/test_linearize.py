import dataclasses
from collections import defaultdict

import pytest
from hypothesis import HealthCheck, assume, given, settings, strategies as st
from hypothesis.internal.conjecture.data import Status

from hypofuzz.dashboard.test import Test
from hypofuzz.database import (
    Phase,
    Report,
    StatusCounts,
    WorkerIdentity,
)


def workers(*, uuid):
    return st.builds(
        WorkerIdentity,
        uuid=st.just(uuid),
        operating_system=st.sampled_from(["darwin", "emscripten", "linux", "win"]),
        python_version=st.just("3.12.10"),
        hypothesis_version=st.just("6.101.2"),
        hypofuzz_version=st.just("24.04.02"),
        pid=st.integers(min_value=0),
        hostname=st.text(st.characters(codec="ascii")),
        pod_name=st.just(None),
        pod_namespace=st.just(None),
        node_name=st.just(None),
        pod_ip=st.just(None),
        container_id=st.just(None),
        git_hash=st.just(None),
    )


_shared_tests = [(b"database_key_" + str(i).encode(), f"nodeid_{i}") for i in range(10)]


def report_inline(
    *,
    database_key=b"inline-database_key",
    nodeid="inline-nodeid",
    elapsed_time=0.0,
    timestamp=0.0,
    worker_uuid="inline-worker_uuid",
    status_counts=None,
    behaviors=0,
    fingerprints=0,
    since_new_behavior=0,
    phase=Phase.GENERATE,
):
    return Report(
        database_key=database_key,
        nodeid=nodeid,
        elapsed_time=elapsed_time,
        timestamp=timestamp,
        worker_uuid=worker_uuid,
        status_counts=StatusCounts() if status_counts is None else status_counts,
        behaviors=behaviors,
        fingerprints=fingerprints,
        since_new_behavior=since_new_behavior,
        phase=phase,
    )


@st.composite
def reports(
    draw,
    *,
    count_workers: int | None = None,
    overlap: bool = False,
    phases: list[Phase] | None = None,
) -> list[Report]:
    # all of this min_size=len(uuids) etc is going to lead to terrible shrinking.
    # But the alternative of while draw(st.booleans()) will generate too-small
    # collections. Use `more` from hypothesis internals?
    database_key, nodeid = draw(st.sampled_from(_shared_tests))
    uuids = draw(
        st.lists(
            st.uuids(version=4), min_size=count_workers or 0, max_size=count_workers
        )
    )
    # determine where each interval will start and end
    # TODO right now none of the generated intervals overlap, implement that for
    # overlap=True
    assert not overlap
    intervals = draw(
        st.lists(
            # Use integers to avoid extreme float values that cause precision issues
            st.tuples(
                st.integers(0, 1_000_000).map(float),
                st.integers(0, 1_000_000).map(float),
            ).map(sorted),
            min_size=len(uuids),
            max_size=len(uuids),
        )
    )
    reports = []
    for uuid, (start_time, end_time) in zip(uuids, intervals, strict=True):
        # reports from the same worker always have monotonically increasing
        # coverage, ninputs, and elapsed_time. timestamp is usually sorted as well,
        # but need not be (and we do not rely on it being sorted).
        ninputs = draw(st.lists(st.integers(min_value=0)).map(sorted))
        timestamps = draw(
            st.lists(
                st.floats(start_time, end_time),
                min_size=len(ninputs),
                max_size=len(ninputs),
            )
        )
        elapsed_times = draw(
            st.lists(
                # Use integers to avoid floating point issues. Tiny floats like
                # 1e-308 can cause timestamp_monotonic collisions when timestamps
                # are large, because max(large_ts, prev_tm + tiny_diff) = large_ts.
                st.integers(0, 1_000_000).map(float),
                min_size=len(ninputs),
                max_size=len(ninputs),
                # strictly monotonically increasing, to avoid ambiguous ties in ordering
                unique=True,
            ).map(sorted)
        )
        for ninput, timestamp, elapsed_time in zip(
            ninputs, timestamps, elapsed_times, strict=True
        ):
            status_counts = StatusCounts()
            # TODO distribute ninput over all the statuses
            status_counts[Status.VALID] = ninput
            phase_st = st.sampled_from(phases) if phases is not None else ...
            report = draw(
                st.builds(
                    Report,
                    database_key=st.just(database_key),
                    nodeid=st.just(nodeid),
                    elapsed_time=st.just(elapsed_time),
                    timestamp=st.just(timestamp),
                    worker_uuid=st.just(uuid),
                    status_counts=st.just(status_counts),
                    behaviors=st.integers(min_value=0),
                    fingerprints=st.integers(min_value=0),
                    since_new_behavior=st.integers(min_value=0),
                    phase=phase_st,
                )
            )
            reports.append(report)

    return reports


def assert_reports_almost_equal(reports1, reports2):
    # like `assert reports1 == reports2`, but handles floating-point errors
    assert len(reports1) == len(reports2)
    for report1, report2 in zip(reports1, reports2, strict=True):
        for attr in set(dataclasses.asdict(report1)) - {
            # (report1 xor report2) might be a ReportWithDiff
            "status_counts_diff",
            "elapsed_time_diff",
            "timestamp_monotonic",
        }:
            v1 = getattr(report1, attr)
            v2 = getattr(report2, attr)
            if attr in ["elapsed_time", "timestamp"]:
                # ignore floating point errors
                assert v1 == pytest.approx(v2), attr
            else:
                assert v1 == v2, attr


def _test_for_reports(reports, *, database_key: bytes = b"", nodeid: str = "") -> Test:
    reports_by_worker = defaultdict(list)
    for report in sorted(reports, key=lambda r: r.elapsed_time):
        reports_by_worker[report.worker_uuid].append(report)
        database_key = report.database_key
        nodeid = report.nodeid

    test = Test(
        database_key=database_key,
        nodeid=nodeid,
        rolling_observations=[],
        corpus_observations=[],
        reports_by_worker=reports_by_worker,
        failures={},
        fatal_failure=None,
    )
    test._check_invariants()
    return test


@pytest.mark.skip(reason="reports() needs more work to behave closer to reality")
@given(reports(count_workers=1))
def test_single_worker(reports):
    assert len({r.worker_uuid for r in reports}) <= 1
    # linearizing reports from a single worker just puts them in a sorted order,
    # ignoring any Phase.REPLAY reports.
    actual = _test_for_reports(reports).linear_reports
    expected = sorted(
        (r for r in reports if r.phase is not Phase.REPLAY),
        key=lambda r: r.elapsed_time,
    )
    assert_reports_almost_equal(actual, expected)


@given(reports(overlap=False))
def test_non_overlapping_reports(reports):
    test = _test_for_reports(reports)
    test._check_invariants()


@given(st.data())
def test_linearize_decomposes_with_addition(data):
    # test that linearize_reports has the following property:
    #
    #   linearize_reports(reports[:i]) followed by add_report(reports[i:])
    #   is the same for all 0 <= i <= len(reports).
    #
    # (forgive the abuse of notation with add_report).

    reports_ = data.draw(reports(count_workers=1))
    # size = 0 and size = 1 are trivial cases (and more importantly, mess up the
    # nodeid in _test_for_reports, since there are no reports to draw the nodeid
    # from).
    assume(len(reports_) > 1)

    i = data.draw(st.integers(1, len(reports_) - 1))
    test1 = _test_for_reports(reports_)

    test2 = _test_for_reports(reports_[:i])
    for report in reports_[i:]:
        test2.add_report(report)
        test2._check_invariants()

    assert test1.linear_status_counts() == test2.linear_status_counts()
    assert test1.linear_elapsed_time() == pytest.approx(test2.linear_elapsed_time())
    assert_reports_almost_equal(test1.linear_reports, test2.linear_reports)


@given(reports())
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_out_of_order_report_invalidates_cache(reports):
    assume(len(reports) > 1)
    test = _test_for_reports(
        [], database_key=reports[0].database_key, nodeid=reports[0].nodeid
    )
    # this is a pretty bad PBT, but asserting the actual property requires
    # reimplementing the linearization logic for the multi-worker case.
    for report in reports:
        test.add_report(report)
        assert len(test.linear_status_counts()) == len(test.linear_reports)
        assert len(test.linear_elapsed_time()) == len(test.linear_reports)

    test._check_invariants()


def test_out_of_order_report_invalidates_cache_explicit():
    test = _test_for_reports(
        [], database_key=b"inline-database_key", nodeid="inline-nodeid"
    )

    test.add_report(report_inline(elapsed_time=1.0, timestamp=1.0))
    assert test.linear_elapsed_time() == [1.0]

    test.add_report(report_inline(elapsed_time=0.5, timestamp=0.5))
    assert test.linear_elapsed_time() == [0.5, 1.0]

    test.add_report(report_inline(elapsed_time=2.0, timestamp=2.0))
    assert test.linear_elapsed_time() == [0.5, 1.0, 2.0]

    test.add_report(report_inline(elapsed_time=0.75, timestamp=0.75))
    assert test.linear_elapsed_time() == [0.5, 0.75, 1.0, 2.0]

    test.add_report(report_inline(elapsed_time=0.25, timestamp=0.25))
    assert test.linear_elapsed_time() == [0.25, 0.5, 0.75, 1.0, 2.0]

    test._check_invariants()


def test_multiple_workers_no_overlap_explicit():
    # multiple workers but no overlap
    test = _test_for_reports(
        [], database_key=b"inline-database_key", nodeid="inline-nodeid"
    )
    test.add_report(
        report_inline(elapsed_time=1.0, timestamp=101, worker_uuid="worker_1")
    )
    test.add_report(
        report_inline(elapsed_time=5.0, timestamp=105, worker_uuid="worker_1")
    )

    test.add_report(
        report_inline(elapsed_time=1.0, timestamp=201, worker_uuid="worker_2")
    )
    test.add_report(
        report_inline(elapsed_time=5.0, timestamp=205, worker_uuid="worker_2")
    )

    assert test.linear_elapsed_time() == [1.0, 5.0, 6.0, 10.0]


def test_multiple_workers_overlap_explicit():
    # multiple workers, with overlap
    test = _test_for_reports(
        [], database_key=b"inline-database_key", nodeid="inline-nodeid"
    )
    test.add_report(
        report_inline(elapsed_time=1.0, timestamp=101, worker_uuid="worker_1")
    )
    assert test.linear_elapsed_time() == [1.0]
    test.add_report(
        report_inline(elapsed_time=5.0, timestamp=105, worker_uuid="worker_1")
    )
    assert test.linear_elapsed_time() == [1.0, 5.0]

    test.add_report(
        report_inline(elapsed_time=1.0, timestamp=102, worker_uuid="worker_2")
    )
    assert test.linear_elapsed_time() == [1.0, 2.0, 6.0]

    test.add_report(
        report_inline(elapsed_time=5.0, timestamp=106, worker_uuid="worker_2")
    )
    assert test.linear_elapsed_time() == [1.0, 2.0, 6.0, 10.0]


def test_desynced_timestamp():
    # test where the difference in timestamps is different than the difference
    # in elapsed_time between reports, which tests our timestamp_monotonic
    # logic
    test = _test_for_reports(
        [], database_key=b"inline-database_key", nodeid="inline-nodeid"
    )
    test.add_report(
        report_inline(elapsed_time=1.0, timestamp=101, worker_uuid="worker_1")
    )
    test.add_report(
        report_inline(elapsed_time=5.0, timestamp=103, worker_uuid="worker_1")
    )

    test.add_report(
        report_inline(elapsed_time=1.0, timestamp=101.1, worker_uuid="worker_2")
    )
    test.add_report(
        report_inline(elapsed_time=2.0, timestamp=101.5, worker_uuid="worker_2")
    )

    assert test.linear_elapsed_time() == [1.0, 2.0, 3.0, 7.0]
    test._check_invariants()


@given(st.data())
@settings(report_multiple_bugs=False)
def test_add_report_order_invariant(data):
    # Exclude REPLAY phase because its inclusion in linear_reports is inherently
    # order-dependent: it depends on the current state of behaviors/fingerprints
    # at the time the report is added.
    reports_ = data.draw(reports(phases=[Phase.GENERATE, Phase.SHRINK]))
    assume(len(reports_) > 1)

    test1 = _test_for_reports(
        [], database_key=reports_[0].database_key, nodeid=reports_[0].nodeid
    )
    for report in reports_:
        test1.add_report(report)

    test2 = _test_for_reports(
        [], database_key=reports_[0].database_key, nodeid=reports_[0].nodeid
    )
    for report in data.draw(st.permutations(reports_)):
        test2.add_report(report)

    assert test1.linear_status_counts() == test2.linear_status_counts()
    assert test1.linear_elapsed_time() == pytest.approx(test2.linear_elapsed_time())
    assert_reports_almost_equal(test1.linear_reports, test2.linear_reports)


def _counts(
    *, interesting: int = 0, valid: int = 0, invalid: int = 0, overrun: int = 0
) -> StatusCounts:
    return StatusCounts(
        {
            Status.INTERESTING: interesting,
            Status.VALID: valid,
            Status.INVALID: invalid,
            Status.OVERRUN: overrun,
        }
    )


def test_order_invariant_explicit():
    test = _test_for_reports(
        [], database_key=b"inline-database_key", nodeid="inline-nodeid"
    )

    # We start with three perfectly standard reports. They arrive to the test
    # out of order; 1, 3, 2. The final result should be the same as if they arrived
    # in order 1, 2, 3.
    report1 = report_inline(
        elapsed_time=1.0,
        timestamp=100,
        status_counts=_counts(valid=1),
    )
    report2 = report_inline(
        elapsed_time=2.0,
        timestamp=101,
        status_counts=_counts(valid=2),
    )
    report3 = report_inline(
        elapsed_time=3.0,
        timestamp=102,
        status_counts=_counts(valid=3),
    )

    test.add_report(report1)
    assert test.linear_status_counts() == [_counts(valid=1)]

    test.add_report(report3)
    assert test.linear_status_counts() == [_counts(valid=1), _counts(valid=3)]

    test.add_report(report2)
    assert test.linear_status_counts() == [
        _counts(valid=1),
        _counts(valid=2),
        _counts(valid=3),
    ]

    reports = test.reports_by_worker["inline-worker_uuid"]
    assert len(reports) == 3

    assert reports[0].elapsed_time == 1.0
    assert reports[0].status_counts_diff == _counts(valid=1)
    assert reports[0].elapsed_time_diff == 1.0

    assert reports[1].elapsed_time == 2.0
    assert reports[1].status_counts_diff == _counts(valid=1)
    assert reports[1].elapsed_time_diff == 1.0

    assert reports[2].elapsed_time == 3.0
    assert reports[2].status_counts_diff == _counts(valid=1)
    assert reports[2].elapsed_time_diff == 1.0


# ============================================================================
# Regression tests for specific bugs found during issue #244 investigation
# ============================================================================


def test_cache_invalidation_on_middle_insert_from_new_worker():
    # Bug: When a new worker's first report is inserted in the middle of
    # linear_reports (not at the end), the cumsum cache was not invalidated.
    # The cache extension logic assumes reports are appended at the end.
    test = _test_for_reports(
        [], database_key=b"inline-database_key", nodeid="inline-nodeid"
    )

    # Add two reports from worker_1
    test.add_report(
        report_inline(elapsed_time=1.0, timestamp=101, worker_uuid="worker_1")
    )
    test.add_report(
        report_inline(elapsed_time=5.0, timestamp=105, worker_uuid="worker_1")
    )
    # Cache is now populated with [1.0, 5.0]
    assert test.linear_elapsed_time() == [1.0, 5.0]

    # Add a report from worker_2 that should be inserted in the MIDDLE
    # (timestamp 102 is between 101 and 105)
    test.add_report(
        report_inline(elapsed_time=1.0, timestamp=102, worker_uuid="worker_2")
    )

    # The cache must be invalidated; if not, we'd incorrectly get [1.0, 5.0, 9.0]
    assert test.linear_elapsed_time() == [1.0, 2.0, 6.0]


def test_recompute_all_subsequent_reports_not_just_one():
    # Bug: When inserting a report out of order, only the immediately next
    # report from the worker was recomputed, not all subsequent reports.
    test = _test_for_reports(
        [], database_key=b"inline-database_key", nodeid="inline-nodeid"
    )

    # Add reports 1, 3, 4 first (skipping 2)
    test.add_report(
        report_inline(
            elapsed_time=1.0,
            timestamp=100,
            status_counts=_counts(valid=10),
        )
    )
    test.add_report(
        report_inline(
            elapsed_time=3.0,
            timestamp=102,
            status_counts=_counts(valid=30),
        )
    )
    test.add_report(
        report_inline(
            elapsed_time=4.0,
            timestamp=103,
            status_counts=_counts(valid=40),
        )
    )

    # Now insert report 2 out of order
    test.add_report(
        report_inline(
            elapsed_time=2.0,
            timestamp=101,
            status_counts=_counts(valid=20),
        )
    )

    # All reports should have correct diffs (each 10 more than the previous)
    reports = test.reports_by_worker["inline-worker_uuid"]
    assert reports[0].status_counts_diff == _counts(valid=10)
    assert reports[1].status_counts_diff == _counts(valid=10)  # 20 - 10
    assert reports[2].status_counts_diff == _counts(valid=10)  # 30 - 20
    assert reports[3].status_counts_diff == _counts(valid=10)  # 40 - 30


def test_remove_and_reinsert_when_sort_key_changes():
    # Bug: When recomputing diffs for subsequent reports, the timestamp_monotonic
    # can change (because it depends on elapsed_time_diff). The report must be
    # removed and re-inserted, not updated in place, to maintain sort order.
    test = _test_for_reports(
        [], database_key=b"inline-database_key", nodeid="inline-nodeid"
    )

    # Set up a scenario where inserting a report changes the timestamp_monotonic
    # of a subsequent report, causing it to move in the sort order.
    #
    # Reports from same worker with same timestamp but different elapsed_times:
    # - Report A: elapsed_time=1.0, timestamp=100 -> tm = max(100, 0+1) = 100
    # - Report C: elapsed_time=3.0, timestamp=100 -> tm = max(100, 100+2) = 102
    #   (initially computed as if B doesn't exist, so diff=2.0 from A)
    #
    # Then insert B in between:
    # - Report B: elapsed_time=2.0, timestamp=100 -> tm = max(100, 100+1) = 101
    # - Report C: must be recomputed -> tm = max(100, 101+1) = 102 (same, but
    #   the elapsed_time_diff changes from 2.0 to 1.0)
    test.add_report(
        report_inline(elapsed_time=1.0, timestamp=100, worker_uuid="worker_1")
    )
    test.add_report(
        report_inline(elapsed_time=3.0, timestamp=100, worker_uuid="worker_1")
    )
    assert test.linear_elapsed_time() == [1.0, 3.0]

    test.add_report(
        report_inline(elapsed_time=2.0, timestamp=100, worker_uuid="worker_1")
    )
    # After inserting B, elapsed times should be cumulative: 1.0, 2.0, 3.0
    assert test.linear_elapsed_time() == [1.0, 2.0, 3.0]

    test._check_invariants()


def test_deterministic_tiebreaker_for_same_timestamp_monotonic():
    # Bug: Reports with the same timestamp_monotonic had non-deterministic order.
    # Now we use (timestamp_monotonic, worker_uuid) as the sort key.
    test = _test_for_reports(
        [], database_key=b"inline-database_key", nodeid="inline-nodeid"
    )

    # Two workers with reports that have the same timestamp_monotonic
    test.add_report(
        report_inline(elapsed_time=1.0, timestamp=100, worker_uuid="worker_b")
    )
    test.add_report(
        report_inline(elapsed_time=1.0, timestamp=100, worker_uuid="worker_a")
    )

    # Should be sorted by worker_uuid when timestamp_monotonic is equal
    assert test.linear_reports[0].worker_uuid == "worker_a"
    assert test.linear_reports[1].worker_uuid == "worker_b"

    test._check_invariants()


def test_search_reports_by_worker_not_linear_reports():
    # Bug: When finding the previous report for diff computation, the code
    # searched in linear_reports (sorted by timestamp_monotonic) instead of
    # reports_by_worker (sorted by elapsed_time).
    #
    # This test creates a scenario where the order differs between the two lists.
    test = _test_for_reports(
        [], database_key=b"inline-database_key", nodeid="inline-nodeid"
    )

    # Worker 1: report at elapsed_time=1.0, timestamp=200
    # Worker 2: report at elapsed_time=5.0, timestamp=100
    #
    # In linear_reports (by timestamp_monotonic): worker_2, worker_1
    # In reports_by_worker: each worker has only its own reports
    test.add_report(
        report_inline(
            elapsed_time=1.0,
            timestamp=200,
            worker_uuid="worker_1",
            status_counts=_counts(valid=10),
        )
    )
    test.add_report(
        report_inline(
            elapsed_time=5.0,
            timestamp=100,
            worker_uuid="worker_2",
            status_counts=_counts(valid=50),
        )
    )

    # Now add a second report from worker_1
    test.add_report(
        report_inline(
            elapsed_time=2.0,
            timestamp=201,
            worker_uuid="worker_1",
            status_counts=_counts(valid=20),
        )
    )

    # The diff should be computed relative to worker_1's first report (valid=10),
    # NOT relative to worker_2's report (valid=50) which might appear "before"
    # in linear_reports.
    worker_1_reports = test.reports_by_worker["worker_1"]
    assert worker_1_reports[1].status_counts_diff == _counts(valid=10)  # 20 - 10

    test._check_invariants()
