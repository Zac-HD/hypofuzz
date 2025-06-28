"""Tests for the hypofuzz library."""

import pytest
from common import collect, collect_names


def test_collects_autouse_fixtures():
    code = """
        @pytest.fixture(autouse=True)
        def fixture(): ...

        @given(st.none())
        def test_autouse(x): ...
        """
    assert collect_names(code) == {"test_autouse"}


def test_collects_autouse_that_uses_fixture():
    code = """
    @pytest.fixture(autouse=True)
    def myfixture(monkeypatch): ...

    @given(st.none())
    def test_autouse(): ...
    """
    assert collect_names(code) == {"test_autouse"}


def test_collects_explicit_autouse_fixture():
    # if the autouse fixture *wasnt* here, this test would not be collected
    # because of the explicit fixture. Make sure this is still true in light
    # of our special logic for autouse fixtures.
    code = """
    @pytest.fixture()
    def myfixture(): ...

    @pytest.fixture(autouse=True)
    def myautousefixture(myfixture): ...

    @given(st.none())
    def test_autouse(myfixture, x): ...
    """

    assert collect_names(code) == {"test_autouse"}


def test_collects_parameterized_tests():
    code = """
    @pytest.mark.parametrize("param", [1, 2, 3])
    @given(st.integers())
    def test_parameterized(param, n):
        pass
    """

    names = {
        (fp.test_fn.__name__, tuple(fp.extra_kwargs.items()))
        for fp in collect(code).fuzz_targets
    }
    assert names == {
        ("test_parameterized", (("param", 1),)),
        ("test_parameterized", (("param", 2),)),
        ("test_parameterized", (("param", 3),)),
    }


@pytest.mark.parametrize(
    "conditions, result",
    [
        # true expressions
        ("True", True),
        ("not False", True),
        ("'sys.version_info > (3, 0, 0)'", True),
        ([True, False], True),
        # false expressions
        ("False", False),
        ("not True", False),
        ("'sys.version_info < (3, 0, 0)'", False),
        ([False, False], False),
    ],
)
def test_skipif_collection(conditions, result):
    if isinstance(conditions, str):
        conditions = [conditions]

    decorators = "\n    ".join(
        f"@pytest.mark.skipif({c}, reason='')" for c in conditions
    )
    code = f"""
    {decorators}
    @given(st.integers())
    def test_a(n):
        pass
    """
    # if (any of) the skipif evaluated to true, we should not have collected this
    # test. Otherwise we should have.
    assert collect_names(code) == (set() if result else {"test_a"})

    # same for a module-level mark
    decorators = ", ".join(f"pytest.mark.skipif({c}, reason='')" for c in conditions)
    code = f"""
    pytestmark = {f'[{decorators}]' if len(conditions) > 1 else decorators}

    @given(st.integers())
    def test_a(n):
        pass
    """
    assert collect_names(code) == (set() if result else {"test_a"})


def test_skip_not_collected():
    code = """
    @pytest.mark.skip
    @given(st.integers())
    def test_a(n):
        pass
    """
    assert not collect_names(code)

    # same for a module-level mark
    code = """
    pytestmark = pytest.mark.skip

    @given(st.integers())
    def test_a(n):
        pass
    """
    assert not collect_names(code)


def test_collects_stateful_test():
    code = """
    names = st.text(min_size=1).filter(lambda x: "/" not in x)

    class NumberModifier(RuleBasedStateMachine):
        folders = Bundle("folders")
        files = Bundle("files")

        @initialize(target=folders)
        def init_folders(self):
            return "/"

        @rule(target=folders, parent=folders, name=names)
        def create_folder(self, parent, name):
            return f"{parent}/{name}"

        @rule(target=files, parent=folders, name=names)
        def create_file(self, parent, name):
            return f"{parent}/{name}"

    NumberModifierTest = NumberModifier.TestCase
    """
    assert collect_names(code) == {"run_state_machine"}


def test_skips_xfail():
    code = """
        @pytest.mark.xfail()
        @given(st.integers())
        def test_a(n):
            pass
        """
    assert not collect_names(code)


def test_skips_parametrized_xfail():
    code = """
        @pytest.mark.xfail
        @pytest.mark.parametrize("param", [1, 2, 3])
        @given(n=st.integers())
        def test_a(param, n):
            pass
        """
    assert not collect_names(code)


def test_collects_custom_xfail():
    code = """
        from functools import wraps

        def custom_xfail(f):
            @wraps(f)
            def wrapped(*args, **kwargs):
                try:
                    return f(*args, **kwargs)
                except Exception:
                    pass
            return wrapped

        @custom_xfail
        @given(st.integers())
        def test_a(n):
            pass
        """
    assert collect_names(code) == {"test_a"}


def test_skips_differing_database():
    code = """
        @given(st.integers())
        @settings(database=None)
        def test_a(n):
            pass
        """
    assert not collect_names(code)

    code = """
        @given(st.integers())
        @settings(database=InMemoryExampleDatabase())
        def test_a(n):
            pass
        """
    assert not collect_names(code)


def test_evaluates_only_closest_skipif(tmp_path):
    # match pytest semantics of short-circuit skipif evaluation.
    file_1 = tmp_path / "skipif_side_effect_test_1"
    file_2 = tmp_path / "skipif_side_effect_test_2"

    code = f"""
    @pytest.mark.skipif(
        \"\"\"(
            (f := open('{file_2}', 'w')) and
            os.write(f.fileno(), b'0') and
            f.close()
        ) or True\"\"\",
        reason="",
    )
    @pytest.mark.skipif(
        \"\"\"(
            (f := open('{file_1}', 'w')) and
            os.write(f.fileno(), b'0') and
            f.close()
        ) or True\"\"\",
        reason="",
    )
    @given(st.none())
    def test_a(a):
        pass
    """

    assert collect_names(code) == set()
    assert file_1.exists()
    assert not file_2.exists()


def test_collects_function_scope_fixtures():
    code = """
    @pytest.fixture()
    def myfixture(): ...

    @given(st.none())
    def test_with_fixture(myfixture, v): ...
    """

    assert collect_names(code) == {"test_with_fixture"}
