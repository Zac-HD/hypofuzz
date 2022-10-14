"""Adaptive fuzzing for property-based tests using Hypothesis."""

import sys
from typing import Any, Dict, FrozenSet, Optional, Set

import attr
import coverage
from hypothesis.internal.escalation import is_hypothesis_file

# The upstream notion of an arc is (int, int) with an implicit filename,
# but HypoFuzz uses an explicit filename as part of the arc.
_ARC_CACHE: Dict[str, Dict[int, Dict[int, "Arc"]]] = {}


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


_POSSIBLE_ARCS: Dict[str, FrozenSet[Arc]] = {}


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


def get_possible_branches(cov: coverage.CoverageData, fname: str) -> FrozenSet[Arc]:
    """Return a list of possible branches for the given file."""
    try:
        return _POSSIBLE_ARCS[fname]
    except KeyError:
        fr = coverage.python.PythonFileReporter(fname, coverage=cov)
        _POSSIBLE_ARCS[fname] = frozenset(
            Arc.make(fname, src, dst) for src, dst in fr.arcs()
        )
        return _POSSIBLE_ARCS[fname]


class CollectionContext:
    """Collect coverage data as a context manager.

    The context manager can be reused; each use updates the ``.branches``
    attribute which will be reset on next use.

    TODO: excluding Hypothesis (and fuzz) files from tracing as well
            as results would be a small performance upgrade.
    """

    def __init__(self, cov: coverage.CoverageData = None) -> None:
        self.cov = cov or get_coverage_instance()
        self.branches: Set[Arc] = set()

    def __enter__(self) -> None:
        self.branches = set()
        self.cov.erase()
        self.cov.start()

    def __exit__(self, _type: Exception, _value: object, _traceback: object) -> None:
        # The `stop()` line shows up as uncovered because we are always running under
        # our *internal* coverage, not *selftest* coverage, here and we don't yet have
        # a way to pass the data back out without breaking pytest-cov's reporting.
        self.cov.stop()  # pragma: no cover
        self.cov.save()
        for f in self.cov._data.measured_files():
            if not is_hypothesis_file(f):
                self.branches.update(
                    Arc.make(f, src, dst) for src, dst in self.cov._data.branches(f)
                )
                # For later: we may want to generalise our notion of an arc to include
                # coverage contexts, for easy Nezha-style differential fuzzing.
                # See `CoverageData.contexts_by_lineno()` for this.

        # If coverage was already running, e.g. for HypoFuzz' self-tests,
        # update that previous instance with the data we just collected.
        # *except* that this pollutes the report with way to much extra data...
        # This would also need to handle the not-under-coverage case, for both
        # correctness and performance.
        # coverage.Coverage.current()._data.update(self.cov._data)


class CustomCollectionContext:
    """Collect coverage data as a context manager.

    The context manager can be reused; each use updates the ``.branches``
    attribute which will be reset on next use.

    TODO: excluding Hypothesis (and fuzz) files from tracing as well
            as results would be a small performance upgrade.
    """

    last: Optional[tuple]

    def trace(self, frame: Any, event: Any, arg: Any) -> Any:
        if event == "line":
            fname = frame.f_code.co_filename
            if not is_hypothesis_file(fname):
                this = (fname, frame.f_lineno)
                self.branches.add((self.last, this))
                self.last = this
        return self.trace

    def __enter__(self) -> None:
        self.last = None
        self.branches: Set[tuple] = set()
        self.prev_trace = sys.gettrace()
        sys.settrace(self.trace)

    def __exit__(self, _type: Exception, _value: object, _traceback: object) -> None:
        sys.settrace(self.prev_trace)
