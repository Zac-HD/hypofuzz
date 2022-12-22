"""CLI and Python API for the fuzzer."""

import sys
from multiprocessing import Process
from typing import NoReturn, Tuple

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
    "--port",
    type=click.IntRange(1, 65535),
    default=9999,
    metavar="PORT",
    help="Optional port for the dashboard (if any)",
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
    port: int,
    unsafe: bool,
    pytest_args: Tuple[str, ...],
) -> NoReturn:
    """[hypofuzz] runs tests with an adaptive coverage-guided fuzzer.

    Unrecognised arguments are passed through to `pytest` to select the tests
    to run, with the additional constraint that only tests using Hypothesis
    but not any pytest fixtures can be fuzzed.

    This process will run forever unless stopped with e.g. ctrl-C.
    """
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
    if numprocesses > len(tests) and not unsafe:
        numprocesses = len(tests)

    testnames = "\n    ".join(t.nodeid for t in tests)
    print(f"using up to {numprocesses} processes to fuzz:\n    {testnames}\n")  # noqa

    if dashboard:
        from .dashboard import start_dashboard_process

        Process(target=start_dashboard_process, kwargs={"port": port}).start()

    processes = []
    for i in range(numprocesses):
        nodes = {t.nodeid for t in (tests if unsafe else tests[i::numprocesses])}
        p = Process(
            target=_fuzz_several,
            kwargs={"pytest_args": pytest_args, "nodeids": nodes, "port": port},
        )
        p.start()
        processes.append(p)
    for p in processes:
        p.join()
    print("Found a failing input for every test!", file=sys.stderr)  # noqa: T201
    sys.exit(1)
    raise NotImplementedError("unreachable")
