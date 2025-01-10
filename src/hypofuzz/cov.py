"""Adaptive fuzzing for property-based tests using Hypothesis."""

import sys
import types
from functools import cache
from typing import Any, Optional

import attr
import coverage
import hypothesis
from hypothesis.internal.escalation import belongs_to

import hypofuzz

# The upstream notion of an arc is (int, int) with an implicit filename,
# but HypoFuzz uses an explicit filename as part of the arc.
_ARC_CACHE: dict[str, dict[int, dict[int, "Arc"]]] = {}


@attr.s(frozen=True, slots=True)
class Arc:
    fname: str = attr.ib()
    start_line: int = attr.ib()
    end_line: int = attr.ib()

    @staticmethod
    def make(fname: str, start: int, end: int) -> "Arc":
        try:
            return _ARC_CACHE[fname][start][end]
        except KeyError:
            self = Arc(fname, start, end)
            _ARC_CACHE.setdefault(fname, {}).setdefault(start, {})[end] = self
            return self


_POSSIBLE_ARCS: dict[str, frozenset[Arc]] = {}


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


def get_possible_branches(cov: coverage.CoverageData, fname: str) -> frozenset[Arc]:
    """Return a list of possible branches for the given file."""
    try:
        return _POSSIBLE_ARCS[fname]
    except KeyError:
        fr = coverage.python.PythonFileReporter(fname, coverage=cov)
        _POSSIBLE_ARCS[fname] = frozenset(
            Arc.make(fname, src, dst) for src, dst in fr.arcs()
        )
        return _POSSIBLE_ARCS[fname]


is_hypothesis_file = belongs_to(hypothesis)
is_hypofuzz_file = belongs_to(hypofuzz)


@cache
def should_trace(fname: str) -> bool:
    return not (is_hypothesis_file(fname) or is_hypofuzz_file(fname))


# use 3.12's sys.monitoring where possible, and sys.settrace otherwise.
class CustomCollectionContext:
    """Collect coverage data as a context manager.

    The context manager can be reused; each use updates the ``.branches``
    attribute which will be reset on next use.
    """

    # tool_id = 1 is designated for coverage, but we intentionally choose a
    # non-reserved tool id so we can co-exist with coverage tools.
    tool_id: int = 3
    tool_name: str = "hypofuzz"
    last: Optional[tuple]

    if sys.version_info[:2] >= (3, 12):
        events = {
            sys.monitoring.events.LINE: "trace_line",
        }

    def trace_pre_312(self, frame: Any, event: Any, arg: Any) -> Any:
        if event == "line":
            fname = frame.f_code.co_filename
            if should_trace(fname):
                this = (fname, frame.f_lineno)
                self.branches.add((self.last, this))
                self.last = this
        return self.trace_pre_312

    def trace_line(self, code: types.CodeType, line_number: int) -> None:
        fname = code.co_filename
        if not should_trace(fname):
            # this function is only called on 3.12+, but we want to avoid an
            # assertion to that effect for performance.
            return sys.monitoring.DISABLE  # type: ignore

        this = (fname, line_number)
        self.branches.add((self.last, this))
        self.last = this

    def __enter__(self) -> None:
        self.last = None
        self.branches: set[tuple] = set()

        if sys.version_info[:2] < (3, 12):
            self.prev_trace = sys.gettrace()
            sys.settrace(self.trace_pre_312)
            return

        sys.monitoring.use_tool_id(self.tool_id, self.tool_name)
        for event, callback_name in self.events.items():
            sys.monitoring.set_events(self.tool_id, event)
            callback = getattr(self, callback_name)
            sys.monitoring.register_callback(self.tool_id, event, callback)

    def __exit__(self, _type: Exception, _value: object, _traceback: object) -> None:
        if sys.version_info[:2] < (3, 12):
            sys.settrace(self.prev_trace)
            return

        sys.monitoring.free_tool_id(self.tool_id)
        for event in self.events:
            sys.monitoring.register_callback(self.tool_id, event, None)
