from hypothesis import given, strategies as st

from hypofuzz.coverage import _BRANCH_CACHE, Branch, Location

locations = st.builds(Location)


@given(locations, locations)
def test_branch_make(start, end):
    branch = Branch.make(start, end)
    assert branch.start == start
    assert branch.end == end


@given(locations, locations)
def test_branch_cache(start, end):
    _BRANCH_CACHE.clear()
    branch1 = Branch.make(start, end)
    branch2 = Branch.make(start, end)
    assert branch1 is branch2


def test_branch_str_same_file():
    branch = Branch(("a", 2, 3), ("a", 5, 6))
    assert str(branch) == "a:2:3::5:6"


def test_branch_str_different_file():
    branch = Branch(("a", 2, 3), ("b", 5, 6))
    assert str(branch) == "a:2:3::b:5:6"
