"""CLI and Python API for the fuzzer."""
import io
from contextlib import redirect_stdout
from typing import Iterable, NoReturn, Tuple

import click
import psutil
import pytest
from hypothesis.extra.cli import main as hypothesis_cli_root

from .hy import FuzzProcess, fuzz_several


class _ItemsCollector:
    """A pytest plugin which grabs all the fuzzable tests at the end of collection."""

    def __init__(self):
        self.fuzz_targets = []

    def pytest_collection_finish(self, session: pytest.Session) -> None:
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
                item.obj, test_id=item.nodeid, extra_kw=extra_kw
            )
            self.fuzz_targets.append(fuzz)


def _get_hypothesis_tests_with_pytest(args: Iterable[str]) -> Iterable[FuzzProcess]:
    """Find the hypothesis-only test functions run by pytest.

    This basically uses `pytest --collect-only -m hypothesis $args`.
    """
    collector = _ItemsCollector()
    with redirect_stdout(io.StringIO()):
        pytest.main(
            args=["--collect-only", "-m=hypothesis", *args], plugins=[collector],
        )
    return collector.fuzz_targets


@hypothesis_cli_root.command()  # type: ignore
@click.option(
    "-n",
    "--numprocesses",
    type=int,
    # we match the -n auto behaviour of pytest-xdist by default
    default=psutil.cpu_count(logical=False) or psutil.cpu_count() or 1,
    show_default="all available cores",
)
@click.argument("pytest_args", nargs=-1)
def fuzz(numprocesses: int, pytest_args: Tuple[str, ...]) -> NoReturn:
    """[hypofuzz] runs tests with an adaptive coverage-guided fuzzer.

    Unrecognised arguments are passed through to `pytest` to select the tests
    to run, with the additional constraint that only tests using Hypothesis
    but not any pytest fixtures can be fuzzed.

    This process will run forever unless stopped with e.g. ctrl-C.
    """
    if numprocesses < 1:
        raise click.UsageError(f"Minimum --numprocesses is one, but got {numprocesses}")
    for arg in ("-n", "--numprocesses"):  # can we get this list automatically?
        if arg in (pytest_args):
            raise click.UsageError(
                f"{arg} must come before the arguments passed through to pytest"
            )

    tests = list(_get_hypothesis_tests_with_pytest(pytest_args))
    if not tests:
        raise click.UsageError("No property-based tests were collected")
    numprocesses = max(numprocesses, len(tests))

    testnames = "\n    ".join(t._test_fn_name for t in tests)
    print(f"using up to {numprocesses} processes to fuzz:\n    {testnames}\n")  # noqa
    fuzz_several(*tests, numprocesses=numprocesses)

    raise NotImplementedError("unreachable")
