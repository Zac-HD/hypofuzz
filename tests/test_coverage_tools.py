"""Tests for the hypofuzz library."""

import hypofuzz.cov


def test_can_get_possible_arcs():
    c = hypofuzz.cov.get_coverage_instance()
    arcs = hypofuzz.cov.get_possible_arcs(c, __file__)
    assert arcs and isinstance(arcs, frozenset)
