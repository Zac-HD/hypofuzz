"""CLI and Python API for the fuzzer."""
import click
import psutil

from hypothesis.extra.cli import main as hypothesis_cli_root

import builtins
import importlib
from difflib import get_close_matches
from typing import NoReturn, Callable, Tuple

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


@hypothesis_cli_root.command()
@click.argument("test", required=True, type=obj_name, nargs=-1)
@click.option(
    "-n",
    "--numprocesses",
    type=int,
    # we match the -n auto behaviour of pytest-xdist by default
    default=psutil.cpu_count(logical=False) or psutil.cpu_count() or 1,
    show_default="all available cores",
)
def fuzz(test: Tuple[Callable[..., None], ...], numprocesses: int) -> NoReturn:
    """[hypofuzz] runs tests with an adaptive coverage-guided fuzzer.

    lorem ipsum, etc.
    """
    if numprocesses < 1:
        raise click.UsageError(f"Minimum --numprocesses is one, but got {numprocesses}")
    print(f"not fuzzing {test} with {numprocesses} processes yet, but soon!")  # noqa
    fuzz_several(
        *map(FuzzProcess.from_hypothesis_test, test), numprocesses=numprocesses,
    )
    raise NotImplementedError("unreachable")
