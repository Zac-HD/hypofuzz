"""Tests for the hypofuzz library."""

import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

import hypofuzz


class Version(NamedTuple):
    year: int
    month: int
    patch: int

    @classmethod
    def from_string(cls, string):
        return cls(*map(int, string.split(".")))


@lru_cache
def get_releases():
    pattern = re.compile(r"^## (\d\d\.\d\d\.\d+)$")
    with open(
        Path(__file__).parent.parent / "src" / "hypofuzz" / "docs" / "changelog.md"
    ) as f:
        return tuple(
            Version.from_string(match.group(1))
            for match in map(pattern.match, f)
            if match is not None
        )


def test_last_release_against_changelog():
    last_version = get_releases()[0]
    assert last_version == Version.from_string(hypofuzz.__version__)
    assert (last_version.year, last_version.month) <= date.today().timetuple()[:2]


def test_changelog_is_ordered():
    versions = get_releases()
    assert versions == tuple(sorted(versions, reverse=True))


def test_version_increments_are_correct():
    # We either increment the patch version by one, or increment the calendar parts
    # and reset the patch version to one.
    versions = get_releases()
    for prev, current in zip(versions[1:], versions):
        assert prev < current  # remember that `versions` is newest-first
        if prev.year == current.year and prev.month == current.month:
            assert current.patch == prev.patch + 1, f"{current} does not follow {prev}"
        else:
            assert current.patch == 1, f"{current} does not follow {prev}"
