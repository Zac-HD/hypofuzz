"""CLI and Python API for the fuzzer."""

import os
import sys
from multiprocessing import Process
from typing import NoReturn, Optional

import click
import hypothesis.extra.cli
import psutil
from hypothesis.internal.conjecture.providers import AVAILABLE_PROVIDERS

AVAILABLE_PROVIDERS["hypofuzz"] = "hypofuzz.provider.HypofuzzProvider"


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
    pytest_args: tuple[str, ...],
) -> NoReturn:
    """[hypofuzz] runs tests with an adaptive coverage-guided fuzzer.

    Unrecognised arguments are passed through to `pytest` to select the tests
    to run, with the additional constraint that only Hypothesis tests can be
    fuzzed.

    This process will run forever unless stopped with e.g. ctrl-C.
    """
    dash_proc = None
    if dashboard or dashboard_only:
        from hypofuzz.dashboard.dashboard import start_dashboard_process

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
            n_processes=numprocesses,
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


def _debug_ranges_disabled() -> bool:
    return (
        # -X no_debug_ranges. sys._xoptions is only present on cpython
        (hasattr(sys, "_xoptions") and "no_debug_ranges" in sys._xoptions)
        or os.environ.get("PYTHONNODEBUGRANGES") is not None
        or any(
            v is None
            # only checked on 3.12+
            for v in _debug_ranges_disabled.__code__.co_positions()  # type: ignore
        )
    )


def _fuzz_impl(n_processes: int, pytest_args: tuple[str, ...]) -> None:
    from hypofuzz.hypofuzz import FuzzWorkerHub

    if sys.version_info[:2] >= (3, 12) and _debug_ranges_disabled():
        raise Exception(
            "The current python interpreter lacks position information for its "
            "code, which Hypothesis relies on to track branch coverage.\n\nThis can "
            "happen if you passed -X no_debug_ranges or set the PYTHONNODEBUGRANGES "
            "enviornment variable before running python."
        )

    # Before doing anything with our arguments, we'll check that none
    # of HypoFuzz's arguments will be passed on to pytest instead.
    misplaced: set = set(pytest_args) & set().union(*(p.opts for p in fuzz.params))
    if misplaced:
        plural = "s" * (len(misplaced) > 1)
        names = ", ".join(map(repr, misplaced))
        raise click.UsageError(
            f"fuzzer option{plural} {names} would be passed to pytest instead"
        )

    from hypofuzz.collection import collect_tests

    # With our arguments validated, it's time to actually do the work.
    collection = collect_tests(pytest_args)
    tests = collection.fuzz_targets
    if not tests:
        raise click.UsageError(
            f"No property-based tests were collected. args: {pytest_args}"
        )

    skipped_s = "s" * (len(collection.not_collected) != 1)
    skipped_msg = (
        ""
        if not collection.not_collected
        else f" (skipped {len(collection.not_collected)} test{skipped_s})"
    )
    n_s = "es" * (n_processes != 1)
    tests_s = "s" * (len(tests) != 1)
    print(
        f"using {n_processes} process{n_s} to fuzz {len(tests)} "
        f"test{tests_s}{skipped_msg}"
    )

    hub = FuzzWorkerHub(
        nodeids=[t.nodeid for t in tests],
        pytest_args=pytest_args,
        n_processes=n_processes,
    )
    hub.start()

    print("Found a failing input for every test!", file=sys.stderr)
