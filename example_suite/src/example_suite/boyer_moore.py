from typing import Dict, List


def boyer_moore_search(text: str, pattern: str) -> List[int]:
    """
    Full Boyer-Moore string search algorithm implementation.

    Implements both the bad character rule and good suffix rule for optimal performance.

    Args:
        text: The text to search in
        pattern: The pattern to search for

    Returns:
        List of starting positions where pattern matches in text
    """
    if not pattern:
        return list(range(len(text) + 1))

    n, m = len(text), len(pattern)
    if m > n:
        return []

    bad_char_table = _build_bad_char_table(pattern)
    good_suffix_table = _build_good_suffix_table(pattern)

    matches = []
    i = m - 1  # Position in text

    while i < n:
        j = m - 1  # Position in pattern
        k = i  # Current position in text

        while j >= 0 and text[k] == pattern[j]:
            j -= 1
            k -= 1

        if j == -1:
            matches.append(k + 1)
            i += good_suffix_table[0]
        else:
            bad_char_shift = _get_bad_char_shift(bad_char_table, text[k], j, m)
            good_suffix_shift = good_suffix_table[j + 1]

            shift = max(bad_char_shift, good_suffix_shift)
            i += shift

    return matches


def _build_bad_char_table(pattern: str) -> Dict[str, int]:
    """
    Build the bad character rule table.

    For each character in the pattern, store the rightmost occurrence position
    from the right end of the pattern.
    """
    m = len(pattern)
    table = {}

    for i in range(m - 1):
        table[pattern[i]] = m - 1 - i

    return table


def _get_bad_char_shift(table: Dict[str, int], char: str, j: int, m: int) -> int:
    """
    Calculate shift using bad character rule.

    Args:
        table: Bad character table
        char: Mismatched character from text
        j: Current position in pattern
        m: Length of pattern

    Returns:
        Shift amount
    """
    if char in table:
        return max(1, table[char] - (m - 1 - j))
    else:
        return max(1, m - j)


def _build_border_table(pattern: str) -> List[int]:
    """
    Build the border table for the good suffix rule.

    A border is a proper suffix that is also a proper prefix.
    """
    m = len(pattern)
    border = [0] * (m + 1)

    i = 1
    j = 0

    while i < m:
        if pattern[i] == pattern[j]:
            border[i + 1] = j + 1
            i += 1
            j += 1
        elif j > 0:
            j = border[j]
        else:
            border[i + 1] = 0
            i += 1

    return border


def _build_good_suffix_table(pattern: str) -> List[int]:
    """
    Build the good suffix rule table.

    This table contains shift values for when a good suffix is found.
    """
    m = len(pattern)
    good_suffix = [m] * (m + 1)
    border = _build_border_table(pattern)

    # Case 1: Exact match
    good_suffix[0] = 1

    # Case 2: Good suffix exists
    for i in range(m):
        j = m - border[i + 1]
        if j < m:
            good_suffix[j] = m - 1 - i

    # Case 3: No good suffix, shift by pattern length
    for i in range(1, m):
        if good_suffix[i] == m:
            good_suffix[i] = m - border[i]

    return good_suffix
