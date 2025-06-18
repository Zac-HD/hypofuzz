import itertools
from collections.abc import Sequence
from typing import Any

import pytest
from hypothesis import given, note, strategies as st

from hypofuzz.bayes import (
    BehaviorRates,
    DistributeNodesTarget,
    distribute_nodes,
    softmax,
)


@given(
    st.integers(1, 100),
    st.lists(
        st.builds(
            DistributeNodesTarget,
            nodeid=st.integers(0, 1000).map(lambda n: f"node{n}"),
            rates=st.builds(
                BehaviorRates,
                per_input=st.floats(min_value=0, max_value=10**10, exclude_min=True),
                per_second=st.floats(min_value=0, max_value=10**10, exclude_min=True),
            ),
            e_startup_time=st.floats(min_value=0, max_value=10**10, exclude_min=True),
        ),
        min_size=1,
    ),
)
def test_distribute_nodes(n, targets):
    partitions = distribute_nodes(targets, n=n, current_workers=None)

    total_nodes = sum(len(partition) for partition in partitions)
    assert total_nodes == n if len(targets) < n else len(targets)
    assert all(len(partition) > 0 for partition in partitions)


@given(st.integers(4, 100))
def test_distribute_nodes_more_processes_than_nodes(n):
    # when there are more processes than nodes, we should see the highest value
    # nodes getting assigned to processes first.
    targets = [
        DistributeNodesTarget(
            nodeid=str(i + 1),
            rates=BehaviorRates(per_second=n, per_input=n),
            e_startup_time=0.0,
        )
        for i, n in enumerate([1, 3, 2])
    ]
    assert set(distribute_nodes(targets, n=n)) == set(
        itertools.islice(itertools.cycle([("2",), ("3",), ("1",)]), n)
    )


def _targets(*targets: Sequence[Any]) -> list[DistributeNodesTarget]:
    return [
        DistributeNodesTarget(
            nodeid=nodeid,
            rates=BehaviorRates(per_second=per_second, per_input=per_input),
            e_startup_time=startup_time,
        )
        for nodeid, (per_second, per_input), startup_time in targets
    ]


@pytest.mark.parametrize(
    "targets, n, expected",
    [
        (
            _targets(("a", (1, 1), 0), ("b", (2, 2), 0), ("c", (3, 3), 0)),
            1,
            {("a", "b", "c")},
        ),
        (
            _targets(("a", (1, 1), 0), ("b", (2, 2), 0), ("c", (3, 3), 0)),
            2,
            {("a", "c"), ("b",)},
        ),
        (
            _targets(("a", (1, 1), 0), ("b", (2, 2), 0), ("c", (3, 3), 0)),
            3,
            {("a",), ("b",), ("c",)},
        ),
    ],
)
def test_distribute_nodes_explicit(targets, n, expected):
    assert set(distribute_nodes(targets, n=n)) == expected


@given(st.lists(st.floats(min_value=0, allow_nan=False, allow_infinity=False)))
def test_softmax(values):
    softmaxed = softmax(values)
    note(f"{softmaxed=}")
    assert all(0 <= v <= 1 for v in softmaxed)

    # check that softmax preserves ordering
    for i in range(len(values) - 1):
        if values[i] == values[i + 1]:
            assert softmaxed[i] == softmaxed[i + 1]
        if values[i] < values[i + 1]:
            # note <= and not < here, since softmax may round down small
            # differences in values to 0
            assert softmaxed[i] <= softmaxed[i + 1]
        if values[i] > values[i + 1]:
            assert softmaxed[i] >= softmaxed[i + 1]

    if values:
        assert sum(softmaxed) == pytest.approx(1)


# TODO: test current_workers and e_startup_time, specifically that the penalty for
# a node switching workers works as expected
