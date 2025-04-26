"""CLI and Python API for the fuzzer."""

import sys
import time
from multiprocessing import Pool, Process
from random import Random
from typing import NoReturn, Optional

import click
import hypothesis.extra.cli
import psutil
from sortedcontainers import SortedKeyList

from hypofuzz.collection import collect_tests
from hypofuzz.hypofuzz import FuzzProcess


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

    dash_proc = None
    if dashboard or dashboard_only:
        from hypofuzz.dashboard import start_dashboard_process

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


class FuzzProcessPool:
    def __init__(self, *, targets: list[FuzzProcess], pytest_args, num_processes):
        self.targets = targets
        self.num_processes = num_processes
        self.pytest_args = pytest_args

        self.pool = Pool(processes=num_processes)
        self.random = Random()
        # TODO: make this aware of test runtime, so it adapts for branches-per-second
        #       rather than branches-per-input.
        self.targets = SortedKeyList(targets, lambda t: t.since_new_cov)

    def start(self):
        for _ in range(self.num_processes):
            self._submit_new_task()

    def _callback(self, _result):
        self._submit_new_task()

    def _submit_new_task(self):
        for i, target in enumerate(self.targets):
            if target.has_found_failure:
                self.targets.pop(i)

        # epsilon-greedy sampling
        if self.random.random() < 0.05:
            target = self.targets[self.random.randrange(len(self.targets))]
        else:
            if len(self.targets) > 1 and self.targets.key(
                self.targets[0]
            ) > self.targets.key(self.targets[1]):
                # pay our log-n cost to keep the list sorted
                self.targets.add(self.targets.pop(0))
            target = self.targets[0]

        self.pool.apply_async(
            _fuzz_one_test,
            kwds={"pytest_args": self.pytest_args, "nodeid": target.nodeid},
            callback=self._callback,
            error_callback=self._callback,
        )


def _fuzz_impl(numprocesses: int, pytest_args: tuple[str, ...]) -> None:
    collection_result = collect_tests(pytest_args)
    tests = collection_result.fuzz_targets
    if not tests:
        raise click.UsageError(
            f"No property-based tests were collected. args: {pytest_args}"
        )

    skipped_msg = (
        ""
        if not collection_result.not_collected
        else f" (skipped {len(collection_result.not_collected)} tests)"
    )
    print(
        f"using {numprocesses} processes to fuzz {len(tests)} property-based tests{skipped_msg}"
    )

    pool = FuzzProcessPool(
        targets=tests, pytest_args=pytest_args, num_processes=numprocesses
    )
    pool.start()
    while True:
        time.sleep(999)


def _fuzz_one_test(*, pytest_args, nodeid):
    targets = [t for t in collect_tests(pytest_args).fuzz_targets if t.nodeid == nodeid]
    if len(targets) != 1:
        return

    target = targets[0]
    target.startup()

    for _ in range(1000):
        if target.has_found_failure:
            break
        target.run_one()
