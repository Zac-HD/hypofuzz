"""Tests for the hypofuzz library."""

import json

import pytest
from hypothesis import given, strategies as st


def test_non_property():
    pass


@given(st.integers(), st.integers())
def test_addition(x, y):
    x + y


@given(
    st.recursive(
        st.none() | st.booleans() | st.integers() | st.floats() | st.text(),
        extend=lambda x: st.lists(x, max_size=3)
        | st.dictionaries(st.text(), x, max_size=3),
    )
)
def test_encode_decode(x):
    assert x == json.loads(json.dumps(x))


@pytest.mark.parametrize("p", [1, 2, 3])
@given(h=st.booleans())
def test_hypothesis_and_parametrize(h, p):
    # mixing them doesn't work at the moment, but it could; see interface.py
    # TODO: add tests with fixtures, with multiple parametrize decorators,
    # and with "arg1,arg2" multi-arg parametrize decorators.
    pass


@pytest.mark.parametrize("p", [1, 2])
@given(h=st.booleans())
def test_hypothesis_and_parametrize_single(h, p):
    pass


@pytest.mark.parametrize("x,y", [(1, 2), (3, 4)])
@given(h=st.booleans())
def test_hypothesis_and_parametrize_two_args(h, x, y):
    pass


@pytest.mark.parametrize("x", [1, 2])
@pytest.mark.parametrize("y", [3, 4])
@given(h=st.booleans())
def test_hypothesis_and_parametrize_two_decorators(h, x, y):
    pass
