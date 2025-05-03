"""Tests for the hypofuzz library."""

from hypothesis import given, settings, strategies as st
from hypothesis.database import InMemoryExampleDatabase
from hypothesis.internal.conjecture.data import Status

from hypofuzz.database import HypofuzzDatabase
from hypofuzz.hypofuzz import FuzzProcess


@given(st.integers())
def pbt(x):
    pass


def test_fuzz_one_process():
    # This is a terrible test but better than nothing
    fp = FuzzProcess.from_hypothesis_test(pbt)
    for _ in range(100):
        fp.run_one()

    # We expect that this test will always pass; check that.
    assert fp.status_counts[Status.INTERESTING] == 0


class CustomError(Exception):
    pass


def test_fuzz_one_process_explain_mode():
    hypothesis_db = InMemoryExampleDatabase()

    @given(st.integers(0, 10), st.integers(0, 10))
    @settings(database=hypothesis_db)
    def test_fails(x, y):
        if x:
            raise CustomError(f"x={x}")

    fp = FuzzProcess.from_hypothesis_test(test_fails)
    for _ in range(10):
        fp.run_one()

    db = HypofuzzDatabase(hypothesis_db)
    assert fp.status_counts[Status.INTERESTING] >= 1
    failures = list(db.fetch_failures(fp.database_key))
    assert len(failures) == 1
    representation = db.fetch_failure_representation(fp.database_key, failures[0])
    assert "CustomError" in representation.traceback
    assert representation.call_repr == "test_fails(\n    x=1,\n    y=0,\n)"
