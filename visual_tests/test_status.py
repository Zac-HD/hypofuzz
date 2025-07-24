import pytest
from hypothesis import given, strategies as st


@given(st.integers())
def test_failed(n):
    assert n < 100


@given(st.integers())
def test_running(n):
    pass


@given(st.integers())
def test_skipped_dynamically(n):
    if n > 100:
        pytest.skip()


class TestUnittest:
    @given(st.integers())
    def test_skipped_dynamically(self, n):
        if n > 100:
            pytest.skip()
