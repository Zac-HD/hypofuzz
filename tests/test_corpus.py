"""Tests for the hypofuzz library."""

import sys

import pytest
from common import interesting_origin
from hypothesis import event, given, note, strategies as st
from hypothesis.database import InMemoryExampleDatabase
from hypothesis.internal.observability import ObservationMetadata, TestCaseObservation
from strategies import nodes

from hypofuzz.corpus import (
    Branch,
    Corpus,
    Fingerprint,
    NodesT,
    Status,
    sort_key,
)
from hypofuzz.database import HypofuzzDatabase
from hypofuzz.hypofuzz import FuzzTarget


def behaviors(fnames=st.sampled_from("abc")) -> st.SearchStrategy[frozenset[Branch]]:
    location = st.tuples(fnames, st.integers(0, 3), st.integers(0, 3))
    return st.frozensets(st.tuples(location, location))


def observations(
    statuses=st.sampled_from(Status),
) -> st.SearchStrategy[TestCaseObservation]:
    return st.builds(
        TestCaseObservation,
        type=st.just("test_case"),
        status=statuses.map(
            lambda status: {
                Status.OVERRUN: "gave_up",
                Status.INVALID: "gave_up",
                Status.VALID: "passed",
                Status.INTERESTING: "failed",
            }[status]
        ),
        status_reason=st.just(""),
        representation=st.just(""),
        arguments=st.just({}),
        how_generated=st.just(""),
        features=st.dictionaries(st.text(), st.integers() | st.floats()),
        metadata=st.builds(
            ObservationMetadata,
            traceback=st.just(None),
            reproduction_decorator=st.just(None),
            predicates=st.just({}),
            backend=st.just({}),
            sys_argv=st.just([]),
            os_getpid=st.just(0),
            imported_at=st.just(0.0),
            data_status=statuses,
            interesting_origin=st.builds(interesting_origin, n=st.integers()),
            choice_nodes=st.lists(nodes()).map(tuple),
            choice_spans=st.just(None),
        ),
    )


@given(
    st.lists(
        st.tuples(
            observations(statuses=st.just(Status.VALID)), behaviors(), st.booleans()
        )
    )
)
def test_corpus_consider_coverage(args):
    corpus = Corpus(
        database=HypofuzzDatabase(InMemoryExampleDatabase()), database_key=b""
    )
    total_coverage = set()
    for observation, behaviors, save_observation in args:
        would_change_coverage = corpus.would_change_coverage(
            behaviors, observation=observation
        )
        behaviors_before = len(corpus.behavior_counts)
        fingerprints_before = len(corpus.fingerprints)
        size_before = (
            sort_key(corpus.fingerprints[behaviors])
            if behaviors in corpus.fingerprints
            else None
        )

        corpus.consider_coverage(
            behaviors, observation=observation, save_observation=save_observation
        )
        note(repr(corpus))
        corpus._check_invariants()
        total_coverage.update(behaviors)

        if would_change_coverage:
            assert (
                len(corpus.behavior_counts) > behaviors_before
                or len(corpus.fingerprints) > fingerprints_before
                or (
                    size_before is not None
                    and sort_key(corpus.fingerprints[behaviors]) < size_before
                )
            )
        else:
            assert len(corpus.behavior_counts) == behaviors_before
            assert len(corpus.fingerprints) == fingerprints_before
            assert (
                size_before is None
                or sort_key(corpus.fingerprints[behaviors]) == size_before
            )

    assert total_coverage == set(corpus.behavior_counts)


@given(
    st.lists(
        st.tuples(
            observations(statuses=st.just(Status.VALID)), behaviors(), st.booleans()
        )
    )
)
def test_corpus_covering_nodes(args):
    # the corpus tracks the *minimal* covering example for each branch. so if we
    # ever try a smaller one, the corpus should update.
    corpus = Corpus(
        database=HypofuzzDatabase(InMemoryExampleDatabase()),
        database_key=b"test-corpus-covering-nodes",
    )
    fingerprints: dict[Fingerprint, NodesT] = {}

    for observation, behaviors, save_observation in args:
        corpus.consider_coverage(
            behaviors, observation=observation, save_observation=save_observation
        )
        note(repr(corpus))
        corpus._check_invariants()

        nodes = observation.metadata.choice_nodes
        fingerprint = frozenset(behaviors)
        if fingerprint not in fingerprints:
            fingerprints[fingerprint] = nodes
        if sort_key(nodes) < sort_key(fingerprints[fingerprint]):
            event("updated size")
            fingerprints[fingerprint] = nodes

    assert fingerprints == corpus.fingerprints


@pytest.mark.skipif(
    sys.version_info < (3, 12), reason="different branches without sys.monitoring"
)
def test_corpus_resets_branch_counts_on_new_coverage():
    @given(st.integers())
    def test_a(x):
        if x == 2:
            pass

    process = FuzzTarget.from_hypothesis_test(
        test_a, database=HypofuzzDatabase(InMemoryExampleDatabase())
    )
    process._enter_fixtures()
    provider = process.provider
    process._execute_once(process.new_conjecture_data(choices=[1]))
    # execute again to re-execute the stability queue
    process._execute_once(process.new_conjecture_data())

    for count in range(2, 10):
        process._execute_once(process.new_conjecture_data(choices=[1]))
        # we keep incrementing arc counts if we don't find new coverage
        assert len(provider.corpus.behavior_counts) == 1
        assert list(provider.corpus.behavior_counts.values()) == [count]

    assert not provider._replay_queue
    assert not provider._choices_queue
    process._execute_once(process.new_conjecture_data(choices=[2]))
    assert len(provider._choices_queue) == 1
    # execute again for stability
    process._execute_once(process.new_conjecture_data())
    assert not provider._choices_queue

    # our behavior counts should get reset whenever we discover a new behavior (branch)
    assert len(provider.corpus.behavior_counts) == 2
    assert list(provider.corpus.behavior_counts.values()) == [1, 1]


# TODO it would be nice to write a massive stateful test that covers all of this
# behavior - in addition to each individual test.
