from dataclasses import dataclass

from hypothesis import given, strategies as st

from hypofuzz.utils import k_way_merge


@given(st.lists(st.lists(st.integers(), min_size=1).map(sorted)))
def test_k_way_merge(lists):
    assert k_way_merge(lists) == sorted(sum(lists, []))


@dataclass
class A:
    value: int


def test_k_way_merge_key():
    a1 = A(1)
    a2 = A(2)
    a3 = A(3)
    a4 = A(4)
    a5 = A(5)
    assert k_way_merge([[a1, a3, a4], [a2, a5]], key=lambda x: x.value) == [
        a1,
        a2,
        a3,
        a4,
        a5,
    ]
