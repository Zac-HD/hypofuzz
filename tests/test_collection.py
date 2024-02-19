"""Tests for the hypofuzz library."""

from hypofuzz import interface

TEST_CODE = """
import pytest
from hypothesis import given, settings, strategies as st

@pytest.fixture(autouse=True)
def fixture():
    pass

@given(st.none())
def test_autouse(x):
    pass


@pytest.fixture()
def other_fixture():
    pass

@given(st.none())
def test_with_fixture(x, other_fixture):
    pass
"""


def test_collects_despite_autouse_fixtures(tmp_path):
    test_fname = tmp_path / "test_demo.py"
    test_fname.write_text(TEST_CODE, encoding="utf-8")
    try:
        fps = interface._get_hypothesis_tests_with_pytest(
            ["-p", "no:dash", str(test_fname)]
        )
    except SystemExit as err:
        raise AssertionError from err
    assert len(fps) == 1
