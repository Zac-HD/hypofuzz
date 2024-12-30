"""CLI and Python API for the fuzzer."""

import sys
from multiprocessing import Process
from typing import NoReturn, Optional

import click
import hypothesis.extra.cli
import psutil


@hypothesis.extra.cli.main.command()  # type: ignore
@click.option(
    "-n",
    "--numprocesses",
    type=click.IntRange(1, None),
    metavar="NUM",
    # we match the -n auto behaviour of pytest-xdist by default
    default=psutil.cpu_count(logical=False) or psutil.cpu_count() or 1,
    help="default: all available cores",
)
@click.option(
    "--dashboard/--no-dashboard",
    default=True,
    help="serve / don't serve a live dashboard page",
)
@click.option(
    "-d",
    "--dashboard-only",
    is_flag=True,
    help="serve a live dashboard page without launching associated fuzzing processes",
)
@click.option(
    "--host",
    type=str,
    default="localhost",
    metavar="HOST",
    help="Optional host for the dashboard",
)
@click.option(
    "--port",
    type=click.IntRange(0, 65535),
    default=9999,
    metavar="PORT",
    help="Optional port for the dashboard (if any). 0 to request an arbitrary open port",
)
@click.option(
    "--unsafe",
    is_flag=True,
    help="Allow concurrent execution of each test (dashboard may report wrong results)",
)
@click.argument(
    "pytest_args",
    nargs=-1,
    metavar="[-- PYTEST_ARGS]",
)
def fuzz(
    numprocesses: int,
    dashboard: bool,
    dashboard_only: bool,
    host: Optional[str],
    port: Optional[int],
    unsafe: bool,
    pytest_args: tuple[str, ...],
) -> NoReturn:
    """[hypofuzz] runs tests with an adaptive coverage-guided fuzzer.

    Unrecognised arguments are passed through to `pytest` to select the tests
    to run, with the additional constraint that only tests using Hypothesis
    but not any pytest fixtures can be fuzzed.

    This process will run forever unless stopped with e.g. ctrl-C.
    """
    dash_proc = None
    if dashboard or dashboard_only:
        from .dashboard import start_dashboard_process

        dash_proc = Process(
            target=start_dashboard_process,
            kwargs={"host": host, "port": port, "pytest_args": pytest_args},
        )
        dash_proc.start()

        if dashboard_only:
            dash_proc.join()
            sys.exit(1)

    try:
        _fuzz_impl(
            numprocesses=numprocesses,
            unsafe=unsafe,
            pytest_args=pytest_args,
        )
    except BaseException:
        if dash_proc:
            dash_proc.kill()
        raise
    finally:
        if dash_proc:
            dash_proc.join()
    sys.exit(1)
    raise NotImplementedError("unreachable")


def _fuzz_impl(numprocesses: int, unsafe: bool, pytest_args: tuple[str, ...]) -> None:
    # Before doing anything with our arguments, we'll check that none
    # of HypoFuzz's arguments will be passed on to pytest instead.
    misplaced: set = set(pytest_args) & set().union(*(p.opts for p in fuzz.params))
    if misplaced:
        plural = "s" * (len(misplaced) > 1)
        names = ", ".join(map(repr, misplaced))
        raise click.UsageError(
            f"fuzzer option{plural} {names} would be passed to pytest instead"
        )

    from .interface import _fuzz_several, _get_hypothesis_tests_with_pytest

    # With our arguments validated, it's time to actually do the work.
    tests = _get_hypothesis_tests_with_pytest(pytest_args)
    if not tests:
        raise click.UsageError("No property-based tests were collected")
    print(f"{tests=}")
    if numprocesses > len(tests) and not unsafe:
        numprocesses = len(tests)

    testnames = "\n    ".join(t.nodeid for t in tests)
    print(f"using up to {numprocesses} processes to fuzz:\n    {testnames}\n")

    if numprocesses <= 1:
        _fuzz_several(pytest_args=pytest_args, nodeids=[t.nodeid for t in tests])
    else:
        processes = []
        for i in range(numprocesses):
            nodes = {t.nodeid for t in (tests if unsafe else tests[i::numprocesses])}
            p = Process(
                target=_fuzz_several,
                kwargs={"pytest_args": pytest_args, "nodeids": nodes},
            )
            p.start()
            processes.append(p)
        for p in processes:
            p.join()
    print("Found a failing input for every test!", file=sys.stderr)
