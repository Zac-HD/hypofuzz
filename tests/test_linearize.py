import dataclasses
from collections import defaultdict
from typing import Optional

import pytest
from hypothesis import given, strategies as st
from hypothesis.internal.conjecture.data import Status

from hypofuzz.dashboard import Test
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


@st.composite
def reports(
    draw, *, count_workers: Optional[int] = None, overlap: bool = False
) -> list[Report]:
    # all of this min_size=len(uuids) etc is going to lead to terrible shrinking.
    # But the alternative of while draw(st.booleans()) will generate too-small
    # collections. Use `more` from hypothesis internals?
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
        # coverage, timestamps, and elapsed_time
        ninputs = draw(st.lists(st.integers(min_value=0)).map(sorted))
        timestamps = draw(
            st.lists(
                st.floats(start_time, end_time),
                min_size=len(ninputs),
                max_size=len(ninputs),
            ).map(sorted)
        )
        elapsed_times = draw(
            st.lists(
                # limit to reasonably-sized floats, we don't care about fp
                # precision loss
                st.floats(0, 2**30),
                min_size=len(ninputs),
                max_size=len(ninputs),
            ).map(sorted)
        )
        for ninput, timestamp, elapsed_time in zip(ninputs, timestamps, elapsed_times):
            status_counts = StatusCounts()
            # TODO distribute ninput over all the statuses
            status_counts[Status.VALID] = ninput
            report = draw(
                st.builds(
                    Report,
                    # TODO draw consistent database_key and nodeid per-worker
                    database_key=st.just(b""),
                    nodeid=st.just(""),
                    elapsed_time=st.just(elapsed_time),
                    timestamp=st.just(timestamp),
                    worker=workers(uuid=uuid),
                    status_counts=st.just(status_counts),
                    branches=st.integers(min_value=0),
                    since_new_branch=st.integers(min_value=0),
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
            # these attributes might not be computed yet for one of the report
            # lists
            "status_counts_diff",
            "elapsed_time_diff",
            "timestamp_monotonic",
        }:
            v1 = getattr(report1, attr)
            v2 = getattr(report2, attr)
            if attr in ["elapsed_time", "timestamp"]:
                # ignore floating point errors
                assert v1 == pytest.approx(v2)
            else:
                assert v1 == v2


def _test_for_reports(reports) -> Test:
    reports_by_worker = defaultdict(list)
    for report in sorted(reports, key=lambda r: r.timestamp):
        reports_by_worker[report.worker.uuid].append(report)

    return Test(
        database_key=b"",
        nodeid="",
        rolling_observations=[],
        corpus_observations=[],
        reports_by_worker=reports_by_worker,
        failure=None,
    )


@given(reports(count_workers=1))
def test_single_worker(reports):
    assert len({r.worker.uuid for r in reports}) <= 1
    # linearizing reports from a single worker just puts them in a sorted order,
    # ignoring any Phase.REPLAY reports.
    actual = _test_for_reports(reports).linear_reports
    expected = sorted(
        (r for r in reports if r.phase is not Phase.REPLAY), key=lambda r: r.timestamp
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
    # the decomposition property is only actually true if we add reports in a sorted
    # order. This may not happen in practice, because e.g. reports from workers may
    # arrive out of order.
    # (e: this may no longer be true now that we correctly drop/handle out-of-order
    # reports in Test.add_report?)
    reports_ = sorted(reports_, key=lambda r: r.timestamp)
    i = data.draw(st.integers(0, len(reports_)))
    test1 = _test_for_reports(reports_)

    test2 = _test_for_reports(reports_[:i])
    for report in reports_[i:]:
        test2.add_report(report)

    assert test1.linear_status_counts(since=None) == test2.linear_status_counts(
        since=None
    )
    assert test1.linear_elapsed_time(since=None) == pytest.approx(
        test2.linear_elapsed_time(since=None)
    )
    assert_reports_almost_equal(test1.linear_reports, test2.linear_reports)
