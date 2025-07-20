import pytest
from hypothesis import Phase, given, settings, strategies as st
from hypothesis.database import InMemoryExampleDatabase


@settings(database=None)
@given(st.integers())
def test_differing_database_1(n):
    pass


@settings(database=InMemoryExampleDatabase())
@given(st.integers())
def test_differing_database_2(n):
    pass


@pytest.mark.skip
@given(st.integers())
def test_skip(n):
    pass


@pytest.mark.skipif(True, reason="unconditional skip")
@given(st.integers())
def test_skipif(n):
    pass


@pytest.mark.xfail
@given(st.integers())
def test_xfail(n):
    pass


@settings(phases=set(Phase) - {Phase.generate})
@given(st.integers())
def test_no_generate_phase(n):
    pass


# TODO: visual tests for _skip_because("error") and _skip_because("not_a_function")
