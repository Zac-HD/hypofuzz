"""Tests for the hypofuzz library."""

import textwrap

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
    assert "CustomError" in observation.metadata["traceback"]
    expected = textwrap.dedent(
        """
    test_fails(
        x=1,
        y=0,  # or any other generated value
    )
    """
    ).strip()
    assert observation.representation == expected
