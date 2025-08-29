from collections.abc import Iterable, Sequence
from typing import List, TypeVar

T = TypeVar("T")


def timsort(values: Sequence[T]) -> List[T]:
    """
    Sort and return a new list using a simplified Timsort-style algorithm.

    - Detects natural runs (non-decreasing or strictly decreasing subsequences)
      and reverses decreasing runs to make them ascending.
    - Merges runs pairwise until a single sorted run remains.

    This is not a full, optimized Timsort implementation but preserves the
    key ideas of natural runs and merging while providing instrumentation.
    """
    n = len(values)
    if n <= 1:
        return list(values)

    runs: List[List[T]] = []

    i = 0
    while i < n:
        j = i + 1
        if j < n and values[j] < values[j - 1]:
            # Strictly decreasing run
            while j < n and values[j] < values[j - 1]:
                j += 1
            run = list(values[i:j])
            run.reverse()  # make ascending
        else:
            # Non-decreasing run (equal values allowed)
            while j < n and values[j] >= values[j - 1]:
                j += 1
            run = list(values[i:j])

        runs.append(run)
        i = j

    if len(runs) == 1:
        return runs[0]

    # Simple pairwise merge until one run remains.
    while len(runs) > 1:
        merged: List[List[T]] = []
        for k in range(0, len(runs), 2):
            if k + 1 == len(runs):
                merged.append(runs[k])
            else:
                merged.append(_merge_two_sorted(runs[k], runs[k + 1]))
        runs = merged

    return runs[0]


def _merge_two_sorted(left: Iterable[T], right: Iterable[T]) -> List[T]:
    li = list(left)
    ri = list(right)
    i = 0
    j = 0
    out: List[T] = []

    while i < len(li) and j < len(ri):
        if li[i] <= ri[j]:
            out.append(li[i])
            i += 1
        else:
            out.append(ri[j])
            j += 1

    if i < len(li):
        out.extend(li[i:])
    if j < len(ri):
        out.extend(ri[j:])

    return out
