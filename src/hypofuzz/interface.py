"""CLI and Python API for the fuzzer."""

import io
import sys
from collections.abc import Iterable
from contextlib import redirect_stdout
from functools import partial
from inspect import signature
from typing import TYPE_CHECKING, get_type_hints

import pytest
from hypothesis.stateful import RuleBasedStateMachine, run_state_machine_as_test

if TYPE_CHECKING:
    # We have to defer imports to within functions here, because this module
    # is a Hypothesis entry point and is thus imported earlier than the others.
    from .hy import FuzzProcess


class _ItemsCollector:
    """A pytest plugin which grabs all the fuzzable tests at the end of collection."""

    def __init__(self) -> None:
        self.fuzz_targets: list[FuzzProcess] = []

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        from .hy import FuzzProcess

        for item in session.items:
            # If the test takes a fixture, we skip it - the fuzzer doesn't have
            # pytest scopes, so we just can't support them.  TODO: note skips.
            manager = item._request._fixturemanager
            fixtureinfo = manager.getfixtureinfo(
                node=item, func=item.function, cls=None
            )

            from _pytest.nodes import Node

            # from pytest 8.3 or thereabouts
            pytest83 = get_type_hints(manager._getautousenames).get("node") == Node
            autouse_names = tuple(
                manager._getautousenames(item if pytest83 else item.nodeid)
            )

            # However, autouse fixtures are ubiquitous enough that we'll skip them;
            # until we get full pytest compatibility it's an expedient approximation.
            # The relevant internals changed in Pytest 8.0, so handle both cases...
            if "fixturenames" not in signature(manager.getfixtureclosure).parameters:
                # pytest ~8
                all_autouse, _ = manager.getfixtureclosure(
                    item, autouse_names, ignore_args=set()
                )
            else:
                # pytest ~6-7
                _, all_autouse, _ = manager.getfixtureclosure(autouse_names, item)

            # Skip any test which:
            # - directly requests a non autouse fixture, or
            # - requests any fixture (in its transitive closure) that isn't autouse
            #
            # We check both to handle the case where a function directly requests
            # a non autouse fixture, *and* that same fixture is requested by an
            # autouse fixture. This function should not be collected.
            if (names := set(fixtureinfo.initialnames).difference(autouse_names)) or (
                names := set(fixtureinfo.name2fixturedefs).difference(all_autouse)
            ):
                print(
                    f"skipping {item=} because of non-autouse fixtures {names}",
                    flush=True,
                )
                continue
            # For parametrized tests, we have to pass the parametrized args into
            # wrapped_test.hypothesis.get_strategy() to avoid trivial TypeErrors
            # from missing required arguments.
            extra_kw = item.callspec.params if hasattr(item, "callspec") else {}
            # Wrap it up in a FuzzTarget and we're done!
            try:
                # Skip state-machine classes, since they're not
                if isinstance(item.obj, RuleBasedStateMachine.TestCase):
                    target = partial(run_state_machine_as_test, item.obj)
                else:
                    target = item.obj
                fuzz = FuzzProcess.from_hypothesis_test(
                    target, nodeid=item.nodeid, extra_kw=extra_kw
                )
                self.fuzz_targets.append(fuzz)
            except Exception as err:
                print("crashed in", item.nodeid, err)


def _get_hypothesis_tests_with_pytest(args: Iterable[str]) -> list["FuzzProcess"]:
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
        print(out.getvalue())
        print(f"Exiting because pytest returned exit code {ret}")
        sys.exit(ret)
    elif not collector.fuzz_targets:
        print(out.getvalue())
    return collector.fuzz_targets


def _fuzz_several(pytest_args: tuple[str, ...], nodeids: list[str]) -> None:
    """Collect and fuzz tests.

    Designed to be used inside a multiprocessing.Process started with the spawn()
    method - requires picklable arguments but works on Windows too.
    """
    # Import within the function to break an import cycle when used as an entry point.
    from .hy import fuzz_several

    tests = [
        t for t in _get_hypothesis_tests_with_pytest(pytest_args) if t.nodeid in nodeids
    ]
    fuzz_several(*tests)
