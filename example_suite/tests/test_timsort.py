from hypothesis import event, given, strategies as st

from example_suite.src.example_suite.timsort import timsort


def _emit_run_events(values: list[int]) -> None:
    n = len(values)
    if n == 0:
        return
    i = 0
    while i < n:
        j = i + 1
        if j < n and values[j] < values[j - 1]:
            while j < n and values[j] < values[j - 1]:
                j += 1
            run_len = j - i
        else:
            while j < n and values[j] >= values[j - 1]:
                j += 1
            run_len = j - i
        event("sorted run lengths", run_len)
        i = j


@given(st.lists(st.integers()))
def test_timsort_matches_builtin(l):
    _emit_run_events(l)
    assert timsort(l) == sorted(l)
