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
    draw, *, count_workers: int | None = None, overlap: bool = False
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
            st.tuples(st.floats(min_value=0), st.floats(min_value=0)).map(sorted),
            min_size=len(uuids),
            max_size=len(uuids),
        )
    )
    reports = []
    for uuid, (start_time, end_time) in zip(uuids, intervals):
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
                # limit to reasonably-sized floats, we don't care about fp
                # precision loss
                st.floats(0, 1_000_000),
                min_size=len(ninputs),
                max_size=len(ninputs),
                # strictly increasing: reports from the same worker always advance
                # elapsed_time by a nonzero amount. Ties in the strategy would
                # generate unrealistic reports with equal elapsed_time but
                # different status_counts, which the linearization logic (and
                # reality) is not designed to handle.
                unique=True,
            ).map(sorted)
        )
        for ninput, timestamp, elapsed_time in zip(ninputs, timestamps, elapsed_times):
            status_counts = StatusCounts()
            # TODO distribute ninput over all the statuses
            status_counts[Status.VALID] = ninput
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
                    phase=...,
                )
            )
            reports.append(report)

    return reports


def assert_reports_almost_equal(reports1, reports2):
    # like `assert reports1 == reports2`, but handles floating-point errors
    assert len(reports1) == len(reports2)
    for report1, report2 in zip(reports1, reports2):
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


# ---------------------------------------------------------------------------
# Regression tests for #244: AssertionError from stale or unsynced linearization
# state when reports arrive across workers with overlapping elapsed_times.
# ---------------------------------------------------------------------------


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


def test_cache_invalidated_on_middle_insert_from_new_worker():
    # Previously, the cumsum cache was only invalidated if the new report was
    # inserted in the middle of linear_reports AND there was already a later
    # report from the same worker. A new worker's first report landing in the
    # middle fell through the crack and left the cache stale.
    test = _test_for_reports(
        [], database_key=b"inline-database_key", nodeid="inline-nodeid"
    )

    test.add_report(
        report_inline(elapsed_time=1.0, timestamp=101, worker_uuid="worker_1")
    )
    test.add_report(
        report_inline(elapsed_time=5.0, timestamp=105, worker_uuid="worker_1")
    )
    # populate the cache
    assert test.linear_elapsed_time() == [1.0, 5.0]

    # worker_2's first-ever report lands between the two worker_1 entries
    test.add_report(
        report_inline(elapsed_time=1.0, timestamp=102, worker_uuid="worker_2")
    )
    assert test.linear_elapsed_time() == [1.0, 2.0, 6.0]
    test._check_invariants()


def test_all_subsequent_worker_reports_are_recomputed():
    # Previously only the immediately-next report from the worker was rebuilt
    # against the out-of-order insert, leaving the tail with stale diffs.
    test = _test_for_reports(
        [], database_key=b"inline-database_key", nodeid="inline-nodeid"
    )
    for elapsed, ts, valid in [(1.0, 100, 10), (3.0, 102, 30), (4.0, 103, 40)]:
        test.add_report(
            report_inline(
                elapsed_time=elapsed, timestamp=ts, status_counts=_counts(valid=valid)
            )
        )

    # insert out-of-order between the first and second existing reports
    test.add_report(
        report_inline(elapsed_time=2.0, timestamp=101, status_counts=_counts(valid=20))
    )

    reports = test.reports_by_worker["inline-worker_uuid"]
    assert [r.status_counts_diff for r in reports] == [
        _counts(valid=10),
        _counts(valid=10),
        _counts(valid=10),
        _counts(valid=10),
    ]
    test._check_invariants()


def test_recompute_uses_reports_by_worker_not_linear_reports():
    # linear_reports is sorted by timestamp_monotonic; reports_by_worker is
    # sorted by elapsed_time. When finding the next report from a worker to
    # recompute, the search must use reports_by_worker - the two orderings
    # diverge when timestamps and elapsed_times aren't aligned across workers.
    test = _test_for_reports(
        [], database_key=b"inline-database_key", nodeid="inline-nodeid"
    )

    # worker_1: elapsed=1 @ timestamp 200, elapsed=3 @ timestamp 201
    # worker_2: elapsed=2 @ timestamp 100 (sits BEFORE worker_1 in linear_reports)
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
            elapsed_time=3.0,
            timestamp=201,
            worker_uuid="worker_1",
            status_counts=_counts(valid=30),
        )
    )
    test.add_report(
        report_inline(
            elapsed_time=2.0,
            timestamp=100,
            worker_uuid="worker_2",
            status_counts=_counts(valid=20),
        )
    )

    # Now insert a worker_1 report at elapsed=2 (between its existing two).
    # The "next" worker_1 report (elapsed=3) comes AFTER worker_2's report in
    # linear_reports; the old search in linear_reports could incorrectly treat
    # worker_2's report as the next one from worker_1 and fail to recompute.
    test.add_report(
        report_inline(
            elapsed_time=2.0,
            timestamp=200.5,
            worker_uuid="worker_1",
            status_counts=_counts(valid=15),
        )
    )

    worker_1_reports = test.reports_by_worker["worker_1"]
    assert [r.status_counts_diff for r in worker_1_reports] == [
        _counts(valid=10),  # 10 - 0
        _counts(valid=5),  # 15 - 10
        _counts(valid=15),  # 30 - 15
    ]
    test._check_invariants()


def test_deterministic_tiebreaker_for_equal_timestamp_monotonic():
    # Two workers submitting reports that land at the same timestamp_monotonic
    # must sort deterministically, so add_report is commutative.
    test_a = _test_for_reports(
        [], database_key=b"inline-database_key", nodeid="inline-nodeid"
    )
    test_b = _test_for_reports(
        [], database_key=b"inline-database_key", nodeid="inline-nodeid"
    )
    reports = [
        report_inline(elapsed_time=1.0, timestamp=100, worker_uuid="worker_a"),
        report_inline(elapsed_time=1.0, timestamp=100, worker_uuid="worker_b"),
    ]
    test_a.add_report(reports[0])
    test_a.add_report(reports[1])
    test_b.add_report(reports[1])
    test_b.add_report(reports[0])

    assert [r.worker_uuid for r in test_a.linear_reports] == [
        r.worker_uuid for r in test_b.linear_reports
    ]
    test_a._check_invariants()
    test_b._check_invariants()


@given(st.data())
@settings(suppress_health_check=[HealthCheck.too_slow], report_multiple_bugs=False)
def test_add_report_is_permutation_invariant(data):
    # The heart of #244: no matter what order a set of reports arrives in,
    # the linearization should produce the same result. Excluding REPLAY is
    # deliberate - its inclusion in linear_reports depends on the running
    # max behaviors/fingerprints and so is intentionally order-dependent.
    reports_ = data.draw(reports())
    assume(len(reports_) > 1)
    reports_ = [r for r in reports_ if r.phase is not Phase.REPLAY]
    assume(len(reports_) > 1)

    permutation = data.draw(st.permutations(reports_))

    test1 = _test_for_reports(
        [], database_key=reports_[0].database_key, nodeid=reports_[0].nodeid
    )
    for report in reports_:
        test1.add_report(report)

    test2 = _test_for_reports(
        [], database_key=reports_[0].database_key, nodeid=reports_[0].nodeid
    )
    for report in permutation:
        test2.add_report(report)

    assert test1.linear_status_counts() == test2.linear_status_counts()
    assert test1.linear_elapsed_time() == pytest.approx(test2.linear_elapsed_time())
    assert_reports_almost_equal(test1.linear_reports, test2.linear_reports)
    test1._check_invariants()
    test2._check_invariants()
