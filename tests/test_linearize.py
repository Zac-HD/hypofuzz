import dataclasses
from typing import Optional

import pytest
from hypothesis import given, strategies as st
from hypothesis.internal.conjecture.data import Status

from hypofuzz.database import (
    Phase,
    Report,
    StatusCounts,
    WorkerIdentity,
    linearize_reports,
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
            status_counts = StatusCounts(dict.fromkeys(Status, 0))
            # TODO distribute ninput over all the statuses
            status_counts[Status.VALID] = ninput
            report = draw(
                st.builds(
                    Report,
                    database_key=st.text(st.characters(codec="ascii")),
                    nodeid=st.text(st.characters(codec="ascii")),
                    elapsed_time=st.just(elapsed_time),
                    timestamp=st.just(timestamp),
                    worker=workers(uuid=uuid),
                    status_counts=st.just(status_counts),
                    branches=st.integers(min_value=0),
                    since_new_cov=st.integers(min_value=0),
                    phase=...,
                )
            )
            reports.append(report)

    return reports


@given(reports(count_workers=1))
def test_single_worker(reports):
    assert len({r.worker.uuid for r in reports}) <= 1
    # linearizing reports from a single worker just puts them in a sorted order,
    # ignorig any Phase.REPLAY reports.
    actual = linearize_reports(reports).reports
    expected = sorted(
        (r for r in reports if r.phase is not Phase.REPLAY), key=lambda r: r.timestamp
    )
    assert len(actual) == len(expected)
    for report1, report2 in zip(actual, expected):
        for attr in dataclasses.asdict(report1):
            v1 = getattr(report1, attr)
            v2 = getattr(report2, attr)
            if attr == "elapsed_time":
                # ignore floating point errors
                assert v1 == pytest.approx(v2)
            else:
                assert v1 == v2


@given(reports(overlap=False))
def test_non_overlapping_reports(reports):
    linearized = linearize_reports(reports).reports
    # If none of the reports overlap, then timestamp, ninputs, and elapsed_time
    # should all be monotonically increasing
    assert all(
        r1.timestamp <= r2.timestamp for r1, r2 in zip(linearized, linearized[1:])
    )
    assert all(
        r1.status_counts <= r2.status_counts
        for r1, r2 in zip(linearized, linearized[1:])
    )
    assert all(
        r1.elapsed_time <= r2.elapsed_time for r1, r2 in zip(linearized, linearized[1:])
    )
