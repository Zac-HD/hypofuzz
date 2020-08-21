"""CLI and Python API for the fuzzer."""
import io
from contextlib import redirect_stdout
from typing import Callable, Iterable, NoReturn, Tuple

import click
import psutil
from hypothesis.extra.cli import main as hypothesis_cli_root

from .hy import FuzzProcess, fuzz_several


def _get_hypothesis_tests_with_pytest(args: Iterable[str]) -> Iterable[Callable]:
    """Find the hypothesis-only test functions run by pytest.

    This basically uses `pytest --collect-only -m hypothesis $args`.
    """
    # TODO: implement an option that doesn't rely on pytest
    import pytest

    class ItemsCollector:
        def pytest_collection_finish(self, session: pytest.Session) -> None:
            # TODO: support pytest.parametrize by reassigning the inner_test with
            # functools.partial and inspection of the MarkSet object.
            # TODO: skip test functions which require fixtures; not worth the trouble.
            items[:] = [x.obj for x in session.items]

    items: list = []
    with redirect_stdout(io.StringIO()):
        pytest.main(
            args=["--collect-only", "-m=hypothesis", *args], plugins=[ItemsCollector()],
        )
    return items


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

    Aside from -n, all arguments are passed through to `pytest` to select the
    tests to run.

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

    testnames = ", ".join(t.__name__ for t in tests)
    print(f"fuzzing {testnames} with up to {numprocesses} processes!\n")  # noqa
    fuzz_several(
        *map(FuzzProcess.from_hypothesis_test, tests), numprocesses=numprocesses,
    )

    raise NotImplementedError("unreachable")
