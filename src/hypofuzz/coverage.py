"""Adaptive fuzzing for property-based tests using Hypothesis."""

import os
import sys
import types
from functools import cache
from pathlib import Path
from typing import Any, Optional

import _pytest
import attr
import coverage
import hypothesis
import pytest
from hypothesis.internal.escalation import belongs_to

import hypofuzz

# filename: {start: {end: arc}}
_ARC_CACHE: dict[str, dict[int, dict[int, "Arc"]]] = {}


@attr.s(frozen=True, slots=True, repr=False)
class Arc:
    fname: str = attr.ib()
    start_line: int = attr.ib()
    end_line: int = attr.ib()

    @staticmethod
    def make(fname: str, start: int, end: int) -> "Arc":
        try:
            return _ARC_CACHE[fname][start][end]
        except KeyError:
            arc = Arc(fname, start, end)
            _ARC_CACHE.setdefault(fname, {}).setdefault(start, {})[end] = arc
            return arc

    def __str__(self) -> str:
        return f"{self.fname}:{self.start_line}::{self.end_line}"

    __repr__ = __str__


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
is_pytest_file = belongs_to(pytest)
is__pytest_file = belongs_to(_pytest)

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
        or is_pytest_file(fname)
        or is__pytest_file(fname)
    )


# use 3.12's sys.monitoring where possible, and sys.settrace otherwise.
class CoverageCollectionContext:
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
        self.branches: set[tuple] = set()
        self.last: Optional[tuple] = None

    def trace_pre_312(self, frame: Any, event: Any, arg: Any) -> Any:
        if event == "line":
            fname = frame.f_code.co_filename
            if should_trace(fname):
                this = (fname, frame.f_lineno)
                self.branches.add((self.last, this))
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

        source = (code.co_filename, s_start_line, s_start_column)
        dest = (code.co_filename, d_start_line, d_start_column)
        self.branches.add((source, dest))

    def __enter__(self) -> None:
        self.last = None
        self.branches = set()

        if sys.version_info[:2] < (3, 12):
            self.prev_trace = sys.gettrace()
            sys.settrace(self.trace_pre_312)
            return

        sys.monitoring.use_tool_id(self.tool_id, self.tool_name)
        sys.monitoring.set_events(self.tool_id, sum(self.events.keys()))
        for event, callback_name in self.events.items():
            callback = getattr(self, callback_name)
            sys.monitoring.register_callback(self.tool_id, event, callback)

    def __exit__(self, _type: Exception, _value: object, _traceback: object) -> None:
        if sys.version_info[:2] < (3, 12):
            sys.settrace(self.prev_trace)
            return

        sys.monitoring.free_tool_id(self.tool_id)
        for event in self.events:
            sys.monitoring.register_callback(self.tool_id, event, None)
