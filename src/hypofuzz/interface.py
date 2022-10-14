"""CLI and Python API for the fuzzer."""
import io
import sys
from contextlib import redirect_stdout, suppress
from functools import partial
from typing import TYPE_CHECKING, Iterable, List, NoReturn, Tuple

import pytest
import requests

if TYPE_CHECKING:
    # We have to defer imports to within functions here, because this module
    # is a Hypothesis entry point and is thus imported earlier than the others.
    from .hy import FuzzProcess


class _ItemsCollector:
    """A pytest plugin which grabs all the fuzzable tests at the end of collection."""

    def __init__(self) -> None:
        self.fuzz_targets: List["FuzzProcess"] = []

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        from .hy import FuzzProcess

        for item in session.items:
            # If the test takes a fixture, we skip it - the fuzzer doesn't have
            # pytest scopes, so we just can't support them.  TODO: note skips.
            if item._request._fixturemanager.getfixtureinfo(
                node=item, func=item.function, cls=None
            ).name2fixturedefs:
                continue
            # For parametrized tests, we have to pass the parametrized args into
            # wrapped_test.hypothesis.get_strategy() to avoid trivial TypeErrors
            # from missing required arguments.
            extra_kw = item.callspec.params if hasattr(item, "callspec") else {}
            # Wrap it up in a FuzzTarget and we're done!
            fuzz = FuzzProcess.from_hypothesis_test(
                item.obj, nodeid=item.nodeid, extra_kw=extra_kw
            )
            self.fuzz_targets.append(fuzz)


def _get_hypothesis_tests_with_pytest(args: Iterable[str]) -> List["FuzzProcess"]:
    """Find the hypothesis-only test functions run by pytest.

    This basically uses `pytest --collect-only -m hypothesis $args`.
    """
    collector = _ItemsCollector()
    out = io.StringIO()
    with redirect_stdout(out):
        ret = pytest.main(
            args=[
                "--collect-only",
                "-m=hypothesis",
                "--pythonwarnings=ignore::pytest.PytestAssertRewriteWarning",
                *args,
            ],
            plugins=[collector],
        )
    if ret:
        print(out.getvalue())  # noqa
        print(f"Exiting because pytest returned exit code {ret}")  # noqa
        sys.exit(ret)
    return collector.fuzz_targets


def _post(port: int, data: dict) -> None:
    with suppress(Exception):
        requests.post(f"http://localhost:{port}/", json=data)


def _fuzz_several(
    pytest_args: Tuple[str, ...], nodeids: List[str], port: int = None
) -> NoReturn:
    """Collect and fuzz tests.

    Designed to be used inside a multiprocessing.Process started with the spawn()
    method - requires picklable arguments but works on Windows too.
    """
    # Import within the function to break an import cycle when used as an entry point.
    from .hy import fuzz_several

    tests = [
        t for t in _get_hypothesis_tests_with_pytest(pytest_args) if t.nodeid in nodeids
    ]
    if port is not None:
        for t in tests:
            t._report_change = partial(_post, port)  # type: ignore

    fuzz_several(*tests)
    raise NotImplementedError("unreachable")
