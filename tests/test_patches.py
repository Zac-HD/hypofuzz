from common import (
    BASIC_TEST_CODE,
    dashboard,
    fuzz,
    setup_test_code,
    wait_for,
    wait_for_test_key,
)
from hypothesis.database import DirectoryBasedExampleDatabase
from hypothesis.extra._patching import _get_patch_for

from hypofuzz.database import HypofuzzDatabase


def test_patches(tmp_path):
    test_dir, db_dir = setup_test_code(tmp_path, BASIC_TEST_CODE)
    db = HypofuzzDatabase(DirectoryBasedExampleDatabase(db_dir))

    with fuzz(test_dir):
        key = wait_for_test_key(db)

        def has_corpus_with_observation():
            choices = list(db.fetch_corpus(key))
            if not choices:
                return False
            for choices in db.fetch_corpus(key):
                observation = db.fetch_corpus_observation(key, choices)
                if observation is not None:
                    return True
            return False

        wait_for(has_corpus_with_observation, interval=0.1)

    for choices in db.fetch_corpus(key):
        observation = db.fetch_corpus_observation(key, choices)

        namespace = {}
        code = (test_dir / "test_a.py").read_text()
        exec(code, namespace)
        test_function = namespace["test"]
        test_function.__code__ = test_function.__code__.replace(
            co_filename=str(test_dir / "test_a.py")
        )
        patch = _get_patch_for(
            test_function,
            [(observation.representation, "via_string")],
            namespace=namespace,
        )
        assert patch is not None

    # and our dashboard also presents the same patches
    with dashboard(test_path=test_dir) as dash:
        patches = dash.patches(nodeid="test_a.py::test")
        assert patches["covering"] is not None
        assert patches["failing"] is None


# TODO test that with a @st.data test, the patch *is* none
