"""Tests for the hypofuzz library."""

from types import SimpleNamespace

from hypothesis import given, note, strategies as st
from hypothesis.database import InMemoryExampleDatabase
from strategies import nodes

from hypofuzz.corpus import Arc, ConjectureResult, HowGenerated, Pool, Status


def branches(
    fnames=st.sampled_from("abc"), lines=st.integers(0, 3)
) -> st.SearchStrategy[Arc]:
    return st.frozensets(st.tuples(fnames, lines, lines))


def results(statuses=st.sampled_from(Status)) -> st.SearchStrategy[ConjectureResult]:
    return st.builds(
        ConjectureResult,
        status=statuses,
        interesting_origin=st.none(),
        output=st.none(),
        extra_information=st.builds(
            SimpleNamespace,
            branches=branches(),
            call_repr=st.just(""),
            reports=st.builds(list),
        ),
        target_observations=st.dictionaries(st.text(), st.integers() | st.floats()),
        tags=st.just(frozenset()),
        examples=st.none(),
        misaligned_at=st.none(),
        nodes=st.lists(nodes()).map(tuple),
    )


@given(
    st.lists(
        st.tuples(
            results(statuses=st.just(Status.VALID)),
            st.sampled_from(HowGenerated),
        ),
        unique_by=lambda r: r[0].nodes,
    )
)
def test_automatic_distillation(ls):
    total_coverage = set()
    pool = Pool(database=InMemoryExampleDatabase(), key=b"")
    for res, how in ls:
        pool.add(res, how)
        note(repr(pool))
        pool._check_invariants()
        total_coverage.update(res.extra_information.branches)
    assert total_coverage == set(pool.arc_counts)
