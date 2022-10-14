"""Tests for the hypofuzz library."""
from hypothesis import given, strategies as st

from hypofuzz.hy import FuzzProcess


@given(st.integers())
def pbt(x):
    pass


def test_fuzz_one_process():
    # This is a terrible test but better than nothing
    fp = FuzzProcess.from_hypothesis_test(pbt)
    for _ in range(100):
        fp.run_one()
