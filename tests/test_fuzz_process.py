"""Tests for the hypofuzz library."""

import textwrap
from types import SimpleNamespace

import pytest
from hypothesis import given, strategies as st
from hypothesis.database import InMemoryExampleDatabase
from hypothesis.internal.conjecture.data import Status

from hypofuzz.database import HypofuzzDatabase
from hypofuzz.hypofuzz import FuzzProcess


def test_fuzz_one_process():
    # This is a terrible test but better than nothing
    @given(st.integers())
    def test_a(x):
        pass

    fp = FuzzProcess.from_hypothesis_test(
        test_a, database=HypofuzzDatabase(InMemoryExampleDatabase())
    )
    for _ in range(100):
        fp.run_one()

    # We expect that this test will always pass; check that.
    assert fp.status_counts[Status.INTERESTING] == 0


class CustomError(Exception):
    pass


def test_fuzz_one_process_explain_mode():
    db = HypofuzzDatabase(InMemoryExampleDatabase())

    @given(st.integers(), st.integers())
    def test_fails(x, y):
        if x:
            raise CustomError(f"x={x}")

    fp = FuzzProcess.from_hypothesis_test(test_fails, database=db)
    while not fp.has_found_failure:
        fp.run_one()

    assert fp.status_counts[Status.INTERESTING] >= 1
    failures = list(db.fetch_failures(fp.database_key, shrunk=True))
    assert len(failures) == 1
    observation = db.fetch_failure_observation(fp.database_key, failures[0])
    assert "CustomError" in observation.metadata.traceback
    expected = textwrap.dedent(
        """
    test_fails(
        x=1,
        y=0,  # or any other generated value
    )
    """
    ).strip()
    assert observation.representation == expected


@pytest.mark.parametrize(
    "pytest_item, expected_property",
    # I can't figure out how to construct an Item (or Function) directly, pytest
    # requires .from_parent.
    [(None, "test_a"), (SimpleNamespace(nodeid="unique_nodeid"), "unique_nodeid")],
)
def test_saved_observation_property(pytest_item, expected_property):
    # we save observations using the pytest item's nodeid if available, or
    # get_pretty_function_description(f) otherwise.
    @given(st.integers())
    def test_a(n):
        pass

    db = HypofuzzDatabase(InMemoryExampleDatabase())
    fp = FuzzProcess.from_hypothesis_test(test_a, database=db, pytest_item=pytest_item)
    assert fp.nodeid == expected_property

    fp.run_one()

    assert all(
        observation.property == expected_property
        for observation in db.fetch_observations(fp.database_key)
    )
