"""Tests for the hypofuzz library."""

import inspect
import tempfile
from pathlib import Path

from hypofuzz import interface
from hypofuzz.hy import FuzzProcess


def collect(code: str) -> list[FuzzProcess]:
    code = (
        inspect.cleandoc(
            """
            import pytest
            from hypothesis import given, strategies as st
            """
        )
        + "\n"
        + inspect.cleandoc(code)
    )
    p = Path(tempfile.mkstemp(prefix="test_", suffix=".py")[1])
    p.write_text(code)
    fps = interface._get_hypothesis_tests_with_pytest([str(p), "-p", "no:dash"])
    p.unlink()
    return fps


def collect_names(code: str) -> set[str]:
    return {fp._test_fn.__name__ for fp in collect(code)}


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


def test_does_not_collect_explicit_fixture_even_if_autouse():
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

    assert collect_names(code) == set()
