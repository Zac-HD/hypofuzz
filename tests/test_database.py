from hypothesis.database import DirectoryBasedExampleDatabase

from hypofuzz.database import HypofuzzDatabase
from common import fuzz, wait_for, write_basic_test_code


def test_database_only_stores_full_entries_in_latest():
    test_dir, db_dir = write_basic_test_code()
    db = HypofuzzDatabase(DirectoryBasedExampleDatabase(db_dir))
    assert not list(db.fetch(b"hypofuzz-test-keys"))

    with fuzz(test_dir=test_dir):
        wait_for(
            lambda: list(db.fetch(b"hypofuzz-test-keys")), timeout=10, interval=0.1
        )
        keys = list(db.fetch(b"hypofuzz-test-keys"))
        # we're only working with a single test
        assert len(keys) == 1
        key = list(keys)[0]

        for i in range(10):
            # wait for db entries to roll in - it's ok if they bunch up and cause
            # some iterations to check the same thing.
            wait_for(
                lambda: len(list(db.fetch_metadata(key))) > i, timeout=10, interval=0.05
            )
            metadata = sorted(db.fetch_metadata(key), key=lambda d: d["elapsed_time"])
            assert "seed_pool" in metadata[-1], metadata
            # allow a leeway of one report due to race conditions: we might save the
            # latest full report before paring the previously-latest (now second)
            # report down to reduced.
            for report in metadata[:-2]:
                assert "nodeid" in report
                assert "seed_pool" not in report
