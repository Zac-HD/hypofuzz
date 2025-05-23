"""Tests for the hypofuzz library."""

import sys
from types import SimpleNamespace

import pytest
from common import interesting_origin
from hypothesis import event, given, note, strategies as st
from hypothesis.database import InMemoryExampleDatabase
from hypothesis.internal.conjecture.data import ConjectureData
from strategies import nodes
from test_coverage import Collector

from hypofuzz.corpus import (
    Branch,
    ConjectureResult,
    Corpus,
    Fingerprint,
    NodesT,
    Status,
    sort_key,
)
from hypofuzz.database import HypofuzzDatabase, Phase
from hypofuzz.hypofuzz import FuzzProcess


def behaviors(fnames=st.sampled_from("abc")) -> st.SearchStrategy[frozenset[Branch]]:
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
            behaviors=behaviors(),
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
    corpus = Corpus(
        database=HypofuzzDatabase(InMemoryExampleDatabase()), database_key=b""
    )
    total_coverage = set()
    for res in args:
        corpus.add(res)
        note(repr(corpus))
        corpus._check_invariants()
        total_coverage.update(res.extra_information.behaviors)
    assert total_coverage == set(corpus.behavior_counts)


@given(corpus_args(statuses=st.just(Status.VALID)))
def test_corpus_covering_nodes(args):
    # the corpus tracks the *minimal* covering example for each branch. so if we
    # ever try a smaller one, the corpus should update.
    corpus = Corpus(
        database=HypofuzzDatabase(InMemoryExampleDatabase()),
        database_key=b"test-corpus-covering-nodes",
    )
    fingerprints: dict[Fingerprint, NodesT] = {}

    for res in args:
        corpus.add(res)
        note(repr(corpus))
        corpus._check_invariants()
        fingerprint = frozenset(res.extra_information.behaviors)
        if fingerprint not in fingerprints:
            fingerprints[fingerprint] = res.nodes
        if sort_key(res.nodes) < sort_key(fingerprints[fingerprint]):
            event("updated size")
            fingerprints[fingerprint] = res.nodes

    assert fingerprints == corpus.fingerprints


@pytest.mark.skipif(sys.version_info < (3, 12), reason="different branches pre-312")
def test_corpus_resets_branch_counts_on_new_coverage():
    db = HypofuzzDatabase(InMemoryExampleDatabase())

    @given(st.integers())
    def test_a(x):
        if x == 2:
            pass

    process = FuzzProcess.from_hypothesis_test(test_a, database=db)
    process._start_phase(Phase.GENERATE)
    for count in range(1, 10):
        process._run_test_on(
            ConjectureData.for_choices([1]), collector=Collector(test_a)
        )
        # we keep incrementing arc counts if we don't find new coverage
        assert len(process.corpus.behavior_counts) == 1
        assert list(process.corpus.behavior_counts.values()) == [count]

    process._run_test_on(ConjectureData.for_choices([2]), collector=Collector(test_a))
    # our arc counts should get reset whenever we discover a new branch
    assert len(process.corpus.behavior_counts) == 2
    assert list(process.corpus.behavior_counts.values()) == [1, 1]


# TODO it would be nice to write a massive stateful test that covers all of this
# behavior - in addition to each individual test.
