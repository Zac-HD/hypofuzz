"""Tests for the hypofuzz library."""

import hypofuzz.cov


def test_can_get_possible_branches():
    c = hypofuzz.cov.get_coverage_instance()
    branches = hypofuzz.cov.get_possible_branches(c, __file__)
    assert branches and isinstance(branches, frozenset)
