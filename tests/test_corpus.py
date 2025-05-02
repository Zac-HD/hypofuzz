"""Tests for the hypofuzz library."""

from collections import defaultdict
from types import SimpleNamespace

from common import interesting_origin
from hypothesis import event, given, note, strategies as st
from hypothesis.database import InMemoryExampleDatabase, choices_to_bytes
from strategies import nodes

from hypofuzz.corpus import (
    Branch,
    ConjectureResult,
    HowGenerated,
    NodesT,
    Pool,
    Status,
    sort_key,
)


def branches(fnames=st.sampled_from("abc")) -> st.SearchStrategy[frozenset[Branch]]:
    location = st.tuples(fnames, st.integers(0, 3), st.integers(0, 3))
    return st.frozensets(st.tuples(location, location))


def results(statuses=st.sampled_from(Status)) -> st.SearchStrategy[ConjectureResult]:
    return st.builds(
        ConjectureResult,
        status=statuses,
        interesting_origin=st.builds(interesting_origin, n=st.integers()),
        output=st.none(),
        extra_information=st.builds(
            SimpleNamespace,
            branches=branches(),
            call_repr=st.just(""),
            reports=st.builds(list),
            traceback=st.just(""),
        ),
        target_observations=st.dictionaries(st.text(), st.integers() | st.floats()),
        tags=st.just(frozenset()),
        spans=st.none(),
        misaligned_at=st.none(),
        nodes=st.lists(nodes()).map(tuple),
    )


def pool_args(statuses=st.sampled_from(Status)):
    return st.lists(
        st.tuples(
            results(statuses=statuses),
            st.sampled_from(HowGenerated),
        ),
        unique_by=lambda r: r[0].nodes,
    )


@given(pool_args(statuses=st.just(Status.VALID)))
def test_pool_coverage_tracking(args):
    pool = Pool(database=InMemoryExampleDatabase(), key=b"")
    total_coverage = set()
    for res, how in args:
        pool.add(res, how)
        note(repr(pool))
        pool._check_invariants()
        total_coverage.update(res.extra_information.branches)
    assert total_coverage == set(pool.branch_counts)


@given(pool_args(statuses=st.just(Status.VALID)))
def test_pool_covering_nodes(args):
    # the pool tracks the *minimal* covering example for each branch. so if we
    # ever try a smaller one, the pool should update.
    pool = Pool(database=InMemoryExampleDatabase(), key=b"")
    covering_nodes: dict[Branch, NodesT] = {}

    for res, how in args:
        pool.add(res, how)
        note(repr(pool))
        pool._check_invariants()
        for branch in res.extra_information.branches:
            if branch not in covering_nodes:
                covering_nodes[branch] = res.nodes
            if sort_key(res.nodes) < sort_key(covering_nodes[branch]):
                event("updated size")
                covering_nodes[branch] = res.nodes

    assert covering_nodes == pool.covering_nodes


@given(pool_args())
def test_interesting_results_are_added_to_database(args):
    db = InMemoryExampleDatabase()
    key = b""
    pool = Pool(database=db, key=key)

    saved = defaultdict(set)
    for res, how in args:
        pool.add(res, how)
        if res.status is not Status.INTERESTING:
            continue

        assert res.interesting_origin in pool.interesting_examples
        origin_nodes = saved[res.interesting_origin]
        # we only save a failure to the db if it's smaller than all other
        # choice sequences we've seen for that failure
        if any(sort_key(res.nodes) >= sort_key(nodes) for nodes in origin_nodes):
            continue

        origin_nodes.add(res.nodes)
        all_nodes = set.union(*saved.values())
        assert set(db.fetch(key)) == {
            choices_to_bytes([n.value for n in nodes]) for nodes in all_nodes
        }


# TODO it would be nice to write a massive stateful test that covers all of this
# behavior - in addition to each individual test.
