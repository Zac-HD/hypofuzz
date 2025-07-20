from hypothesis import given, strategies as st


@given(st.integers())
def test_failed(n):
    assert n < 100


@given(st.integers())
def test_running(n):
    pass
