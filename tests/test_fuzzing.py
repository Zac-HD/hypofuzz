import time

import pytest
from common import fuzz, setup_test_code, wait_for, wait_for_test_key
from hypothesis.database import DirectoryBasedExampleDatabase

from hypofuzz.database import FailureState, HypofuzzDatabase

# high-level tests that fuzzing something does not produce an error


def fuzz_with_no_error(tmp_path, code):
    test_path, db_path = setup_test_code(tmp_path, code)
    db = HypofuzzDatabase(DirectoryBasedExampleDatabase(db_path))

    with fuzz(test_path):
        key = wait_for_test_key(db)
        start = time.time()
        wait_for(
            lambda: len(list(db.fetch_observations(key))) > 5
            or time.time() - start > 2,
            interval=0.1,
        )

    assert not db.fetch_fatal_failure(key)
    for state in [FailureState.FIXED, FailureState.SHRUNK, FailureState.UNSHRUNK]:
        failures = list(db.fetch_failures(key, state=state))
        assert not failures, [
            db.fetch_failure_observation(key, choices, state=state)
            for choices in failures
        ]


@pytest.mark.parametrize(
    "code",
    [
        """
    @given(st.integers())
    def test_trivial(n):
        pass
    """,
        """
    @given(st.floats(allow_infinity=False, allow_nan=False) | st.integers())
    def test_targeting(v):
        target(v)
    """,
    ],
)
def test_fuzz_with_no_error(tmp_path, code):
    fuzz_with_no_error(tmp_path, code)
