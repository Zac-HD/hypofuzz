"""Adaptive fuzzing for property-based tests using Hypothesis."""

import sys
from contextlib import contextmanager
from functools import lru_cache
from typing import Callable, Iterator

import _pytest
import pytest
from hypothesis.internal.escalation import belongs_to, is_hypothesis_file
from pycrunch_trace.client.api import Trace
from pycrunch_trace.filters import CustomFileFilter
from pycrunch_trace.oop.safe_filename import SafeFilename

is_pytest_file = belongs_to(pytest)
is__pytest_file = belongs_to(_pytest)
is_pycrunch_file = belongs_to(sys.modules["pycrunch_trace"])


@lru_cache()
def is_hypofuzz_file() -> Callable:
    # Layer of indirection to avoid import cycles
    import hypofuzz

    return belongs_to(hypofuzz)  # type: ignore


class HypofuzzFileFilter(CustomFileFilter):
    def should_trace(self, filename: str) -> bool:
        return (
            super().should_trace(filename)
            and not filename.endswith(("contextlib.py", "reprlib.py"))
            and not is_hypothesis_file(filename)
            and not is_pytest_file(filename)
            and not is__pytest_file(filename)
            and not is_pycrunch_file(filename)
            and not is_hypofuzz_file()(filename)
        )


# This is kinda evil monkeypatching, but on the other hand it saves the user
# a lot of trouble writing config files for pytrace... so it's fine.
sys.modules[Trace.__module__].CustomFileFilter = HypofuzzFileFilter  # type: ignore


@contextmanager
def record_pytrace(nodeid: str) -> Iterator:
    rr = Trace()
    try:
        rr.start(session_name=str(SafeFilename(nodeid)))
        yield
    finally:
        rr.stop()
