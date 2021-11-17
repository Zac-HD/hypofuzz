from hypothesis import given, strategies as st


def foo(ls):
    if 10 in ls:
        x = ls[0]
    return sum(ls)


@given(st.lists(st.integers()))
def test_add_small(ls):
    r = repr(ls)
    assert foo(ls) < 10
