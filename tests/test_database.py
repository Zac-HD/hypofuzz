import subprocess

from common import BASIC_TEST_CODE, fuzz, setup_test_code, wait_for
from hypothesis import given, strategies as st
from hypothesis.database import (
    DirectoryBasedExampleDatabase,
    InMemoryExampleDatabase,
    choices_from_bytes,
)
from hypothesis.internal.conjecture.data import ConjectureData

from hypofuzz.database import HypofuzzDatabase, Phase, test_keys_key
from hypofuzz.hypofuzz import FuzzProcess


def test_database_stores_reports_and_metadata_correctly(tmp_path):
    # test that things of type Report are saved to reports_key.
    #
    # Nowadays, this is validated by our dataclass parsing step.

    test_dir, db_dir = setup_test_code(tmp_path, BASIC_TEST_CODE)
    db = HypofuzzDatabase(DirectoryBasedExampleDatabase(db_dir))
    assert not list(db.fetch(test_keys_key))

    with fuzz(test_path=test_dir):
        keys = wait_for(lambda: list(db.fetch(test_keys_key)), interval=0.1)
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


def test_database_state():
    db = HypofuzzDatabase(InMemoryExampleDatabase())

    @given(st.integers())
    def test_a(x):
        if x:
            pass

    process = FuzzProcess.from_hypothesis_test(test_a, database=db)
    process._start_phase(Phase.GENERATE)
    process._run_test_on(ConjectureData.for_choices([2]))

    key = process.database_key

    # the database state should be:
    # * database_key.hypofuzz.observations              (1 element)
    # * database_key.hypofuzz.corpus                    (1 element)
    # * database_key.hypofuzz.corpus.<hash>.observation (1 element)
    # * database_key.hypofuzz.reports                   (1 element)
    assert len(db._db.data.keys()) == 4
    assert list(db.fetch_corpus(key)) == [(2,)]

    observations = list(db.fetch_corpus_observations(key, (2,)))
    assert len(observations) == 1
    assert observations[0].property == "test_a"

    reports = list(db.fetch_reports(key))
    assert reports[0].phase is Phase.GENERATE

    # now we run a second input, which is better than the first input in coverage.
    # This should clear out both the corpus and observation entry for the old
    # input.
    # The database state should be:
    # * database_key.hypofuzz.observations              (maybe 2 elements, if > 1 second)
    # * database_key.hypofuzz.corpus                    (1 element) (a new one)
    # * database_key.hypofuzz.corpus.<hash>.observation (1 element) (a new one)
    # * database_key.hypofuzz.reports                   (2 elements)
    process._run_test_on(ConjectureData.for_choices([1]))
    # the key for the deleted observation sticks around in the database, it's
    # just an empty mapping.
    assert len([k for k, v in db._db.data.items() if v]) == 4
    assert list(db.fetch_corpus(key)) == [(1,)]

    observations = list(db.fetch_corpus_observations(key, (1,)))
    assert len(observations) == 1
    assert observations[0].property == "test_a"

    reports = list(db.fetch_reports(key))
    assert len(reports) == 2
    assert reports[0].phase is Phase.GENERATE


def test_adds_failures_to_database():
    db = HypofuzzDatabase(InMemoryExampleDatabase())

    @given(st.integers(0, 10))
    def test_a(x):
        assert x != 10

    process = FuzzProcess.from_hypothesis_test(test_a, database=db)
    for _ in range(50):
        process.run_one()

    failures = list(db.fetch_failures(process.database_key, shrunk=True))
    failures_hypothesis = list(db._db.fetch(process.database_key))
    assert len(failures) == 1
    assert len(failures_hypothesis) == 1
    assert failures[0] == (10,)
    assert choices_from_bytes(failures_hypothesis[0]) == (10,)

    # we should have fully shrunk the failure
    assert not list(db.fetch_failures(process.database_key, shrunk=False))


def test_database_keys_incorporate_parametrization(tmp_path):
    test_code = """
        @pytest.mark.parametrize("x", [1, 2])
        @given(st.integers())
        def test_ints(x, n):
            assert False
        """
    test_dir, db_dir = setup_test_code(tmp_path / "one", test_code)
    db_hypofuzz = HypofuzzDatabase(DirectoryBasedExampleDatabase(db_dir))
    assert not set(db_hypofuzz.fetch(test_keys_key))

    # we split this to explicitly one-test-per-core to not rely on details of
    # node allocation across cores.
    with fuzz(test_path=test_dir, pytest_args=["-k", "test_ints[1]"]):
        wait_for(
            lambda: len(set(db_hypofuzz.fetch(test_keys_key))) == 1,
            interval=0.1,
        )

    with fuzz(test_path=test_dir, pytest_args=["-k", "test_ints[2]"]):
        # this will time out if the test keys are the same across parametrizations
        wait_for(
            lambda: len(set(db_hypofuzz.fetch(test_keys_key))) == 2,
            interval=0.1,
        )

    # test that the keys hypofuzz uses are the same as the ones hypothesis
    # uses. We run pytest on the test file, which fails, causing hypothesis to write
    # the failing choice sequence for each parametrization as a top-level key. These
    # top-level keys should be the same as the hypofuzz keys.
    test_dir, db_dir = setup_test_code(tmp_path / "two", test_code)
    db_hypothesis = DirectoryBasedExampleDatabase(db_dir)
    hypofuzz_keys = set(db_hypofuzz.fetch(test_keys_key))
    assert (
        set(db_hypothesis.fetch(DirectoryBasedExampleDatabase._metakeys_name)) == set()
    )

    subprocess.run(["pytest", str(test_dir)], check=False)
    assert hypofuzz_keys == set(
        db_hypothesis.fetch(DirectoryBasedExampleDatabase._metakeys_name)
    )
