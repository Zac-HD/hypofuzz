import textwrap
import unittest

import _pytest
import pytest
from common import (
    fuzz,
    setup_test_code,
    wait_for,
    wait_for_test_key,
    with_in_hypofuzz_run,
)
from hypothesis import given, strategies as st
from hypothesis.database import DirectoryBasedExampleDatabase, InMemoryExampleDatabase
from hypothesis.internal.conjecture.data import Status

import hypofuzz.corpus
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
@with_in_hypofuzz_run(True)
def test_does_not_shrink_skip_exceptions(monkeypatch, SkipException):
    def get_shrinker(*args, **kwargs):
        raise ValueError("get_shrinker was called")

    monkeypatch.setattr(hypofuzz.hypofuzz, "get_shrinker", get_shrinker)

    @given(st.integers())
    def test_a(n):
        raise SkipException()

    target = FuzzTarget.from_hypothesis_test(
        test_a, database=HypofuzzDatabase(InMemoryExampleDatabase())
    )
    target._enter_fixtures()
    try:
        target.run_one()
    except BaseException as e:
        # if pytest.skip escapes to pytest it will skip the test, and CI will
        # look green. Don't let this happen.
        if isinstance(e, _pytest.outcomes.Skipped):
            raise ValueError(
                "Expected pytest.skip to result in a Status.INTERESTING data"
            )
        raise

    assert target.has_found_failure
    interesting_origin = list(target.provider.corpus.interesting_examples.keys())[0]
    assert interesting_origin.exc_type is SkipException
