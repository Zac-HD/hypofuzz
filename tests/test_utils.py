from hypothesis import given, strategies as st

from hypofuzz.compat import bisect_right
from hypofuzz.utils import fast_bisect_right, k_way_merge


@given(st.data())
def test_k_way_merge(data):
    key = data.draw(st.sampled_from([None, lambda x: x, lambda x: -x]))
    lists = data.draw(
        st.lists(st.lists(st.integers()).map(lambda l: sorted(l, key=key)))
    )
    assert k_way_merge(lists, key=key) == sorted(sum(lists, []), key=key)


@given(st.data())
def test_fast_bisect_right(data):
    key = data.draw(st.sampled_from([None, lambda x: x, lambda x: -x]))
    values = data.draw(st.lists(st.integers()).map(lambda l: sorted(l, key=key)))
    x = data.draw(st.integers())
    assert fast_bisect_right(values, x, key=key) == bisect_right(values, x, key=key)
