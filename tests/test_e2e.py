"""Tests for the hypofuzz library."""

import os
import subprocess
import sys

import pytest
import requests
from common import BASIC_TEST_CODE, dashboard, setup_test_code

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
    test_fname = tmp_path / "test_demo2.py"
    test_fname.write_text(TEST_CODE, encoding="utf-8")

    with dashboard(test_path=tmp_path, numprocesses=numprocesses) as dash:
        resp = requests.get(f"http://localhost:{dash.port}", timeout=2)
        resp.raise_for_status()


@pytest.mark.skipif(sys.version_info < (3, 12), reason="we only check on 3.12+")
def test_raises_without_debug_ranges(tmp_path):
    test_dir, _db_dir = setup_test_code(tmp_path, BASIC_TEST_CODE)

    process = subprocess.run(
        [
            "hypothesis",
            "fuzz",
            "--numprocesses",
            "1",
            "--no-dashboard",
            "--",
            test_dir,
        ],
        env=os.environ | {"PYTHONNODEBUGRANGES": "1"},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert process.returncode == 1
    assert "The current python interpreter lacks position information" in process.stderr
