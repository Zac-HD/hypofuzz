import pytest
from hypothesis import given, strategies as st


@pytest.mark.skip
@given(st.integers())
def test_pytest_skip_is_not_collected(n):
    pass


@pytest.mark.skipif(True, reason="skip unconditionally")
@given(st.integers())
def test_pytest_true_skipif_is_not_collect(n):
    pass
