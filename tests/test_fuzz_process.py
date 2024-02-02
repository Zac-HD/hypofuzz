"""Tests for the hypofuzz library."""

from hypothesis import given, strategies as st
from hypothesis.internal.conjecture.data import Status

from hypofuzz.hy import FuzzProcess


@given(st.integers())
def pbt(x):
    pass


def test_fuzz_one_process():
    # This is a terrible test but better than nothing
    fp = FuzzProcess.from_hypothesis_test(pbt)
    for _ in range(100):
        fp.run_one()

    # We expect that this test will always pass; check that.
    assert fp.status_counts[Status.INTERESTING.name] == 0


class CustomError(Exception):
    pass


@given(st.integers(0, 10), st.integers(0, 10))
def failing_pbt(x, y):
    if x:
        raise CustomError(f"x={x}")


def test_fuzz_one_process_explain_mode():
    # This is a terrible test but better than nothing
    fp = FuzzProcess.from_hypothesis_test(failing_pbt)
    for _ in range(10):
        fp.run_one()

    # Check that we got the expected failure, including message + explain-mode output.
    assert fp.status_counts[Status.INTERESTING.name] >= 1
    (call_repr, _, _, tb_repr), *rest = fp._json_description["failures"]
    assert not rest  # expected only one failure
    assert tb_repr.endswith("test_fuzz_process.CustomError: x=1\n")
    assert call_repr == "failing_pbt(\n    x=1,\n    y=0,\n)"
