from hypothesis import given, strategies as st

from example_suite.src.example_suite.boyer_moore import boyer_moore_search


@given(st.text(), st.text(min_size=1))
def test_boyer_moore_correctness(text, pattern):
    """
    Test that our Boyer-Moore implementation finds all matches that exist in the text.
    """
    builtin_matches = set()
    start = 0
    while True:
        pos = text.find(pattern, start)
        if pos == -1:
            break
        builtin_matches.add(pos)
        start = pos + 1

    # check that boyer moore matches the bruteforce version
    assert set(boyer_moore_search(text, pattern)) == builtin_matches
