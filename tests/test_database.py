from common import BASIC_TEST_CODE, fuzz, wait_for, write_test_code
from hypothesis.database import DirectoryBasedExampleDatabase

from hypofuzz.database import HypofuzzDatabase


def test_database_stores_reports_and_metadata_correctly():
    # test that things of type Report are saved to reports_key, and things of type
    # Metadata are saved to metadata_key.
    #
    # Nowadays, this is validated by our dataclass parsing step.

    test_dir, db_dir = write_test_code(BASIC_TEST_CODE)
    db = HypofuzzDatabase(DirectoryBasedExampleDatabase(db_dir))
    assert not list(db.fetch(b"hypofuzz-test-keys"))

    with fuzz(test_path=test_dir):
        wait_for(
            lambda: list(db.fetch(b"hypofuzz-test-keys")), timeout=10, interval=0.1
        )
        keys = list(db.fetch(b"hypofuzz-test-keys"))
        # we're only working with a single test
        assert len(keys) == 1
        key = list(keys)[0]

        previous_size = 0
        for _ in range(5):
            # wait for new db entries to roll in
            wait_for(
                lambda: len(list(db.fetch_reports(key))) > previous_size,
                timeout=15,
                interval=0.05,
            )
            list(db.fetch_reports(key))
            list(db.fetch_metadata(key))


def test_database_keys_are_unique_by_nodeid():
    test_dir, db_dir = write_test_code(
        """
        @pytest.mark.parametrize("x", [1, 2])
        @given(st.integers())
        def test_ints(x, n):
            pass
        """
    )
    db = HypofuzzDatabase(DirectoryBasedExampleDatabase(db_dir))
    assert not list(db.fetch(b"hypofuzz-test-keys"))

    with fuzz(test_path=test_dir, n=2):
        # this will time out if the test keys are the same across parametrizations
        wait_for(
            lambda: len(list(db.fetch(b"hypofuzz-test-keys"))) == 2,
            timeout=10,
            interval=0.1,
        )
