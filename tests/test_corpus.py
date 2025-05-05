"""Tests for the hypofuzz library."""

from types import SimpleNamespace

from common import interesting_origin
from hypothesis import event, given, note, settings, strategies as st
from hypothesis.database import InMemoryExampleDatabase
from hypothesis.internal.conjecture.data import ConjectureData
from strategies import nodes
from test_coverage import Collector

from hypofuzz.corpus import (
    Branch,
    ConjectureResult,
    Corpus,
    NodesT,
    Status,
    sort_key,
)
from hypofuzz.database import Phase
from hypofuzz.hypofuzz import FuzzProcess


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
            reports=st.builds(list),
            traceback=st.just(""),
        ),
        target_observations=st.dictionaries(st.text(), st.integers() | st.floats()),
        tags=st.just(frozenset()),
        spans=st.none(),
        misaligned_at=st.none(),
        nodes=st.lists(nodes()).map(tuple),
    )


def corpus_args(statuses=st.sampled_from(Status)):
    return st.lists(results(statuses=statuses), unique_by=lambda r: r.nodes)


@given(corpus_args(statuses=st.just(Status.VALID)))
def test_corpus_coverage_tracking(args):
    corpus = Corpus(hypothesis_database=InMemoryExampleDatabase(), database_key=b"")
    total_coverage = set()
    for res in args:
        corpus.add(res)
        note(repr(corpus))
        corpus._check_invariants()
        total_coverage.update(res.extra_information.branches)
    assert total_coverage == set(corpus.branch_counts)


@given(corpus_args(statuses=st.just(Status.VALID)))
def test_corpus_covering_nodes(args):
    # the corpus tracks the *minimal* covering example for each branch. so if we
    # ever try a smaller one, the corpus should update.
    corpus = Corpus(hypothesis_database=InMemoryExampleDatabase(), database_key=b"")
    covering_nodes: dict[Branch, NodesT] = {}

    for res in args:
        corpus.add(res)
        note(repr(corpus))
        corpus._check_invariants()
        for branch in res.extra_information.branches:
            if branch not in covering_nodes:
                covering_nodes[branch] = res.nodes
            if sort_key(res.nodes) < sort_key(covering_nodes[branch]):
                event("updated size")
                covering_nodes[branch] = res.nodes

    assert covering_nodes == corpus.covering_nodes


def test_corpus_resets_branch_counts_on_new_coverage():
    hypothesis_db = InMemoryExampleDatabase()

    @given(st.integers())
    @settings(database=hypothesis_db)
    def test_a(x):
        if x == 2:
            pass

    process = FuzzProcess.from_hypothesis_test(test_a)
    process._start_phase(Phase.GENERATE)
    for count in range(1, 10):
        process._run_test_on(
            ConjectureData.for_choices([1]), collector=Collector(test_a)
        )
        # we keep incrementing arc counts if we don't find new coverage
        assert process.corpus.branch_counts == {((3, 11), (3, 11)): count}

    process._run_test_on(ConjectureData.for_choices([2]), collector=Collector(test_a))
    # our arc counts should get reset whenever we discover a new branch
    assert process.corpus.branch_counts == {
        ((3, 11), (3, 11)): 1,
        ((3, 11), (4, 12)): 1,
    }


# TODO it would be nice to write a massive stateful test that covers all of this
# behavior - in addition to each individual test.
