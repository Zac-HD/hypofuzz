from hypothesis import given, strategies as st
import itertools

from hypofuzz.bayes import distribute_nodes


@given(
    st.lists(
        st.tuples(
            st.integers(0, 1000).map(lambda n: f"node{n}"),
            st.floats(min_value=0, allow_infinity=False, exclude_min=True),
        ),
        min_size=1,
    ),
    st.integers(1, 100),
)
def test_distribute_nodes(items, n):
    nodeids = [item[0] for item in items]
    estimators = [item[1] for item in items]
    partitions = distribute_nodes(nodeids, estimators, n=n)

    total_nodes = sum(len(partition) for partition in partitions)
    assert total_nodes == n if len(nodeids) < n else len(nodeids)
    assert all(len(partition) > 0 for partition in partitions)


@given(st.integers(4, 100))
def test_distribute_nodes_more_processes_than_nodes(n):
    # when there are more processes than nodes, we should see the highest value
    # nodes getting assigned to processes first.
    assert distribute_nodes(["1", "2", "3"], [1, 3, 2], n=n) == tuple(
        itertools.islice(itertools.cycle([("2",), ("3",), ("1",)]), n)
    )
