"""Tests for the hypofuzz library."""

import pytest
import requests

from hypofuzz import entrypoint

TEST_CODE = """
from hypothesis import given, settings, strategies as st
from hypothesis.database import InMemoryExampleDatabase

settings.register_profile("ephemeral", settings(database=InMemoryExampleDatabase()))
settings.load_profile("ephemeral")

n = st.integers(0, 127)

@given(a=n, b=n, c=n)
def test(a, b, c):
    # Expected number of cases to find this is (128**3)/2 using random search,
    # but with fuzzing is about (128 + 2*128 * 3*128)/2, many many times faster.
    # Our heuristics only complicated that a bit, but it's still only going to
    # work as a e2e test if the coverage guidance is working.
    if a == 3:
        if b == 4:
            assert c != 5
"""


@pytest.mark.parametrize("numprocesses", [1])  # consider multiprocess someday?
def test_end_to_end(numprocesses, tmp_path):
    """An end-to-end test to start the fuzzer and access the dashboard."""
    test_fname = tmp_path / "test_demo.py"
    test_fname.write_text(TEST_CODE, encoding="utf-8")
    dash_proc = entrypoint._fuzz_impl(
        numprocesses=numprocesses,
        dashboard=True,
        port=7777,
        unsafe=False,
        pytest_args=["-p", "no:dash", str(test_fname)],
    )
    assert dash_proc
    resp = requests.get("http://localhost:7777", allow_redirects=True, timeout=10)
    resp.raise_for_status()
    dash_proc.kill()
    dash_proc.join()
