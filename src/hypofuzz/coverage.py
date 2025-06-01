"""Adaptive fuzzing for property-based tests using Hypothesis."""

import os
import sys
import types
from functools import cache
from pathlib import Path
from typing import Any, NamedTuple, Optional

import _pytest
import attr
import attrs
import coverage
import hypothesis
import pluggy
import pytest
import sortedcontainers
import watchdog
from hypothesis.internal.escalation import belongs_to

import hypofuzz

# (start_file, end_file): {start: {end: branch}}
_BRANCH_CACHE: dict[
    tuple[str, str],
    dict[tuple[int, Optional[int]], dict[tuple[int, Optional[int]], "Branch"]],
] = {}


# NamedTuple is ~2x faster to instantiate and uses ~3% less memory than a slotted
# dataclass. We're storing a *lot* of branches, so this is worthwhile.
class Location(NamedTuple):
    filename: str
    line: int
    # column might be None if we're on pre-3.12
    column: Optional[int]


class Branch(NamedTuple):
    start: Location
    end: Location

    @staticmethod
    def make(start: Location, end: Location) -> "Branch":
        start_file = start.filename
        start_key = (start.line, start.column)
        end_file = end.filename
        end_key = (end.line, end.column)
        try:
            return _BRANCH_CACHE[start_file, end_file][start_key][end_key]
        except KeyError:
            branch = Branch(start, end)
            _BRANCH_CACHE.setdefault((start_file, end_file), {}).setdefault(
                start_key, {}
            )[end_key] = branch
            return branch

    def __str__(self) -> str:
        location1 = f"{self.start[1]}:{self.start[2]}"
        location2 = f"{self.end[1]}:{self.end[2]}"
        if self.start[0] == self.end[0]:
            return f"{self.start[0]}:{location1}::{location2}"
        return f"{self.start[0]}:{location1}::{self.end[0]}:{location2}"

    # __repr__ = __str__ triggers a mypy bug (?)
    def __repr__(self) -> str:
        return self.__str__()


def get_coverage_instance(**kwargs: Any) -> coverage.Coverage:
    # See https://coverage.readthedocs.io/en/latest/api_coverage.html
    c = coverage.Coverage(
        data_file=None,  # write nothing to disk
        cover_pylib=True,  # measure stdlib and package code too
        branch=True,  # branch coverage
        config_file=False,  # ignore any config files
        **kwargs,
    )
    c._init()
    return c


is_hypothesis_file = belongs_to(hypothesis)
is_hypofuzz_file = belongs_to(hypofuzz)
is_pluggy_file = belongs_to(pluggy)
is_pytest_file = belongs_to(pytest)
is__pytest_file = belongs_to(_pytest)
is_sortedcontainers_file = belongs_to(sortedcontainers)
is_watchdog_file = belongs_to(watchdog)
# hypofuzz doesn't use attrs, but hypothesis does.
# TODO migrate hypothesis off attrs and then drop this blacklist?
is_attr_file = belongs_to(attr)
is_attrs_file = belongs_to(attrs)


stdlib_path = Path(os.__file__).parent


def is_stdlib_file(fname: str) -> bool:
    return fname.startswith(str(stdlib_path))


def is_generated_file(fname: str) -> bool:
    # some examples:
    # <frozen posixpath>
    # <attrs generated init hypothesis.internal.conjecture.choice.ChoiceNode>
    return fname.startswith("<") and fname.endswith(">")


@cache
def should_trace(fname: str) -> bool:
    return not (
        is_hypothesis_file(fname)
        or is_hypofuzz_file(fname)
        or is_stdlib_file(fname)
        or is_generated_file(fname)
        or is_pluggy_file(fname)
        or is_pytest_file(fname)
        or is__pytest_file(fname)
        or is_sortedcontainers_file(fname)
        or is_watchdog_file(fname)
        or is_attr_file(fname)
        or is_attrs_file(fname)
    )


# use 3.12's sys.monitoring where possible, and sys.settrace otherwise.
class CoverageCollector:
    """Collect coverage data as a context manager.

    The context manager can be reused; each use updates the ``.branches``
    attribute which will be reset on next use.
    """

    # tool_id = 1 is designated for coverage, but we intentionally choose a
    # non-reserved tool id so we can co-exist with coverage tools.
    # out of an abundance of caution, we also avoid conflicting with hypothesis'
    # tool_id = 3, thought I don't expect this to be problematic.
    tool_id: int = 4
    tool_name: str = "hypofuzz"

    if sys.version_info[:2] >= (3, 12):
        events = {
            sys.monitoring.events.BRANCH: "trace_branch",
        }

    def __init__(self) -> None:
        self.branches: set[Branch] = set()
        self.last: Optional[Location] = None

    def trace_pre_312(self, frame: Any, event: Any, arg: Any) -> Any:
        if event == "line":
            fname = frame.f_code.co_filename
            if should_trace(fname):
                # we don't get column information pre-3.11 (see co_positions)
                this = Location(fname, frame.f_lineno, None)
                if self.last is not None:
                    self.branches.add(Branch.make(self.last, this))
                self.last = this
        return self.trace_pre_312

    def trace_branch(
        self, code: types.CodeType, source_offset: int, dest_offset: int
    ) -> None:
        if not should_trace(code.co_filename):
            return sys.monitoring.DISABLE  # type: ignore

        # I *think* that all bytecode offsets are multiples of 2 nowadays, though
        # I'm not sure when this changed. 3.6 moved to 16bit (2 byte) "wordcode",
        # https://docs.python.org/3/whatsnew/3.6.html (grep for wordcode), but
        # this comment implies 3.10 instead, though that may be specific to
        # co_positions:
        # https://github.com/python/cpython/blob/281fc338fdf57ef119e213bf1b2c7722
        # 61c359c1/Lib/inspect.py#L1555-L1560
        #
        # Either way, we're on 3.12+ if this function gets called.
        assert source_offset % 2 == 0
        assert dest_offset % 2 == 0
        positions = list(code.co_positions())  # type: ignore # new in 3.11
        (s_start_line, _s_end_line, s_start_column, _s_end_column) = positions[
            source_offset // 2
        ]
        (d_start_line, _d_end_line, d_start_column, _d_end_column) = positions[
            dest_offset // 2
        ]
        # if anything is None, skip this branch. This can happen for various reasons.
        # Most notably with -X no_debug_ranges, in which case we will get *zero*
        # position information.
        # TODO detect when python is running with no_debug_ranges and warn or error?
        #
        # see https://docs.python.org/3/reference/datamodel.html#codeobject.co_positions.
        if (
            s_start_line is None
            or d_start_line is None
            or s_start_column is None
            or d_start_column is None
        ):
            return sys.monitoring.DISABLE  # type: ignore

        source = Location(code.co_filename, s_start_line, s_start_column)
        dest = Location(code.co_filename, d_start_line, d_start_column)
        self.branches.add(Branch.make(source, dest))

    def __enter__(self) -> "CoverageCollector":
        self.last = None
        self.branches = set()

        if sys.version_info[:2] < (3, 12):
            self.prev_trace = sys.gettrace()
            sys.settrace(self.trace_pre_312)
            return self

        assert (
            existing_tool := sys.monitoring.get_tool(self.tool_id)
        ) is None, f"tool id {self.tool_id} already registered by tool {existing_tool}"
        sys.monitoring.use_tool_id(self.tool_id, self.tool_name)
        sys.monitoring.set_events(self.tool_id, sum(self.events.keys()))
        for event, callback_name in self.events.items():
            callback = getattr(self, callback_name)
            sys.monitoring.register_callback(self.tool_id, event, callback)

        return self

    def __exit__(self, _type: Exception, _value: object, _traceback: object) -> None:
        if sys.version_info[:2] < (3, 12):
            sys.settrace(self.prev_trace)
            return

        sys.monitoring.free_tool_id(self.tool_id)
        for event in self.events:
            sys.monitoring.register_callback(self.tool_id, event, None)
