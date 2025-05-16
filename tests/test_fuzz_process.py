"""Tests for the hypofuzz library."""

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

    @given(st.integers(0, 10), st.integers(0, 10))
    def test_fails(x, y):
        if x:
            raise CustomError(f"x={x}")

    fp = FuzzProcess.from_hypothesis_test(test_fails, database=db)
    for _ in range(10):
        fp.run_one()

    assert fp.status_counts[Status.INTERESTING] >= 1
    failures = list(db.fetch_failures(fp.database_key, shrunk=True))
    assert len(failures) == 1
    observation = db.fetch_failure_observation(fp.database_key, failures[0])
    assert "CustomError" in observation.metadata["traceback"]
    assert observation.representation == "test_fails(\n    x=1,\n    y=0,\n)"
