"""CLI and Python API for the fuzzer."""
import click
import psutil

from hypothesis.extra.cli import main as hypothesis_cli_root

import builtins
import importlib
from difflib import get_close_matches
from typing import NoReturn, Tuple
import subprocess

from .hy import FuzzProcess, fuzz_several


# TODO: delegate to pytest collection via
# https://click.palletsprojects.com/en/7.x/advanced/#forwarding-unknown-options


def obj_name(s: str) -> object:
    """Get the property test indicated by string s."""
    # TODO: work out the API we actually want for this.
    # currently it's just copied from the ghostwriter CLI.
    try:
        return importlib.import_module(s)
    except ImportError:
        pass
    if "." not in s:
        modulename, module, funcname = "builtins", builtins, s
    else:
        modulename, funcname = s.rsplit(".", 1)
        try:
            module = importlib.import_module(modulename)
        except ImportError:
            raise click.UsageError(
                f"Failed to import the {modulename} module for introspection.  "
                "Check spelling and your Python import path, or use the Python API?"
            )
    try:
        return getattr(module, funcname)
    except AttributeError:
        public_names = [name for name in vars(module) if not name.startswith("_")]
        matches = get_close_matches(funcname, public_names)
        raise click.UsageError(
            f"Found the {modulename!r} module, but it doesn't have a "
            f"{funcname!r} attribute."
            + (f"  Closest matches: {matches!r}" if matches else "")
        )


def _get_hypothesis_tests_with_pytest(args):
    """Find the hypothesis-only test functions run by pytest.

    This basically uses `pytest --collect-only -m hypothesis $args`.
    """
    import pytest
    from _pytest.config import _prepareconfig

    # TODO: suppress pytest output here for quietness
    args = ["--collect-only", "--quiet", "-m=hypothesis", *args]
    config = _prepareconfig(args=args, plugins=None)
    try:
        session = pytest.Session.from_config(config)
        config._do_configure()
        config.hook.pytest_sessionstart(session=session)
        config.hook.pytest_collection(session=session)
        # TODO: can support mark.parametrize via partial + inner_test and helpers from
        # https://github.com/pytest-dev/pytest/blob/master/src/_pytest/mark/structures.py
        # Note that we might (??) need to set db key like Hypothesis too.
        return [item.obj for item in session.items]
    finally:
        config.hook.pytest_sessionfinish(session=session, exitstatus=session.exitstatus)
        config._ensure_unconfigure()
        print()  # noqa


@hypothesis_cli_root.command()
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

    for arg in ("-n", "--numprocesses"):  # can we automate this somehow?
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
