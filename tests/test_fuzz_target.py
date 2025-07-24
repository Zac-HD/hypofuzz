import textwrap
import unittest

import _pytest
import pytest
from common import (
    fuzz,
    setup_test_code,
    wait_for,
    wait_for_test_key,
)
from hypothesis import given, strategies as st
from hypothesis.database import DirectoryBasedExampleDatabase, InMemoryExampleDatabase
from hypothesis.internal.conjecture.data import Status

from hypofuzz.database import FailureState, HypofuzzDatabase
from hypofuzz.hypofuzz import FailedFatally, FuzzTarget


def test_fuzz_one_process():
    # This is a terrible test but better than nothing
    @given(st.integers())
    def test_a(x):
        pass

    fp = FuzzTarget.from_hypothesis_test(
        test_a, database=HypofuzzDatabase(InMemoryExampleDatabase())
    )
    fp._enter_fixtures()
    for _ in range(100):
        fp.run_one()

    # We expect that this test will always pass; check that.
    assert fp.provider.status_counts[Status.INTERESTING] == 0


class CustomError(Exception):
    pass


def test_fuzz_one_process_explain_mode():
    db = HypofuzzDatabase(InMemoryExampleDatabase())

    @given(st.integers(), st.integers())
    def test_fails(x, y):
        if x:
            raise CustomError(f"x={x}")

    fp = FuzzTarget.from_hypothesis_test(test_fails, database=db)
    fp._enter_fixtures()
    while not fp.has_found_failure:
        fp.run_one()

    assert fp.provider.status_counts_mutated[Status.INTERESTING] == 1
    failures = list(db.fetch_failures(fp.database_key, state=FailureState.SHRUNK))
    assert len(failures) == 1
    observation = db.fetch_failure_observation(
        fp.database_key, failures[0], state=FailureState.SHRUNK
    )
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


def test_observations_use_pytest_nodeid(tmp_path):
    code = """
    @given(st.integers())
    def test_abcd(n):
        pass
    """
    test_path, db_path = setup_test_code(tmp_path, code)
    db = HypofuzzDatabase(DirectoryBasedExampleDatabase(db_path))

    with fuzz(test_path):
        key = wait_for_test_key(db)
        wait_for(lambda: len(list(db.fetch_observations(key))) > 0, interval=0.1)
        assert all(
            observation.property == "test_a.py::test_abcd"
            for observation in db.fetch_observations(key)
        ), [obs.property for obs in db.fetch_observations(key)]


def test_raises_failed_fatally_in_enter_fixtures():
    @given(st.integers())
    def test_a(this_param_is_not_filled, n):
        pass

    target = FuzzTarget.from_hypothesis_test(
        test_a, database=HypofuzzDatabase(InMemoryExampleDatabase())
    )
    with pytest.raises(FailedFatally):
        target._enter_fixtures()
    assert target.failed_fatally


@pytest.mark.parametrize(
    "SkipException",
    [
        _pytest.outcomes.Skipped,
        unittest.SkipTest,
        pytest.param(Exception, marks=pytest.mark.xfail),
    ],
)
def test_fuzz_target_reraises_skip_exception(SkipException):
    # this isn't a great test, because it doesn't exercise our logic inside
    # FuzzWorker for saving skip exception observation, or we stop fuzzing a
    # FuzzTarget which finds a skip exception.
    @given(st.integers())
    def test_a(n):
        raise SkipException()

    target = FuzzTarget.from_hypothesis_test(
        test_a, database=HypofuzzDatabase(InMemoryExampleDatabase())
    )
    target._enter_fixtures()
    with pytest.raises(SkipException):
        target.run_one()
