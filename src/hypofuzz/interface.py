"""CLI and Python API for the fuzzer."""

import io
import sys
from collections.abc import Iterable
from contextlib import redirect_stdout
from inspect import signature
from typing import TYPE_CHECKING, get_type_hints

import pytest
from _pytest.nodes import Item, Node
from _pytest.skipping import evaluate_condition
from hypothesis.stateful import get_state_machine_test
from packaging import version

if TYPE_CHECKING:
    # We have to defer imports to within functions here, because this module
    # is a Hypothesis entry point and is thus imported earlier than the others.
    from .hy import FuzzProcess

pytest8 = version.parse(pytest.__version__) >= version.parse("8.0.0")


def has_true_skipif(item: Item) -> bool:
    # multiple @skipif decorators are treated as an OR.
    for mark in item.iter_markers("skipif"):
        result, _reason = evaluate_condition(item, mark, condition=mark.args[0])
        if result:
            return True
    return False


class _ItemsCollector:
    """A pytest plugin which grabs all the fuzzable tests at the end of collection."""

    def __init__(self) -> None:
        self.fuzz_targets: list[FuzzProcess] = []

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        from .hy import FuzzProcess

        for item in session.items:
            if not isinstance(item, pytest.Function):
                print(f"skipping non-pytest.Function item {item=}")
                continue
            if list(item.iter_markers("skip")):
                print(f"skipping {item=} due to an @skip mark")
                continue
            if has_true_skipif(item):
                print(f"skipping {item=} due to a true @skipif mark")
                continue
            # If the test takes a fixture, we skip it - the fuzzer doesn't have
            # pytest scopes, so we just can't support them.  TODO: note skips.
            manager = item._request._fixturemanager
            fixtureinfo = manager.getfixtureinfo(
                node=item, func=item.function, cls=None
            )

            # from pytest 8.3 or thereabouts
            pytest83 = get_type_hints(manager._getautousenames).get("node") == Node
            autouse_names = set(
                manager._getautousenames(item if pytest83 else item.nodeid)  # type: ignore
            )

            # However, autouse fixtures are ubiquitous enough that we'll skip them;
            # until we get full pytest compatibility it's an expedient approximation.
            # The relevant internals changed in Pytest 8.0, so handle both cases...
            if "fixturenames" not in signature(manager.getfixtureclosure).parameters:
                # pytest ~8
                all_autouse_, _ = manager.getfixtureclosure(
                    item, autouse_names, ignore_args=set()  # type: ignore
                )
            else:
                # pytest ~6-7
                _, all_autouse_, _ = manager.getfixtureclosure(autouse_names, item)  # type: ignore

            all_autouse = set(all_autouse_)
            # from @pytest.mark.parametrize. Pytest gives us the params and their
            # values directly, so we can pass them as extra kwargs to FuzzProcess.
            params = item.callspec.params if hasattr(item, "callspec") else {}
            param_names = set(params)
            extra_kw = params

            # Skip any test which:
            # - directly requests a non autouse fixture, or
            # - requests any fixture (in its transitive closure) that isn't autouse
            #
            # We check both to handle the case where a function directly requests
            # a non autouse fixture, *and* that same fixture is requested by an
            # autouse fixture. This function should not be collected.
            #
            # We also ignore any arguments from @pytest.mark.parametrize, which we know how to handle.
            if (
                names := set(fixtureinfo.initialnames).difference(
                    autouse_names | param_names
                )
            ) or (
                names := set(fixtureinfo.name2fixturedefs).difference(
                    all_autouse | param_names
                )
            ):
                print(
                    f"skipping {item=} because of non-autouse fixtures {names}",
                    flush=True,
                )
                continue
            # Wrap it up in a FuzzTarget and we're done!
            try:
                if hasattr(item.obj, "_hypothesis_state_machine_class"):
                    assert (
                        extra_kw == {}
                    ), "Not possible for RuleBasedStateMachine.TestCase to be parametrized"
                    runTest = item.obj
                    StateMachineClass = runTest._hypothesis_state_machine_class
                    target = get_state_machine_test(  # type: ignore
                        StateMachineClass,
                        # runTest is a function, not a bound method, under pyest7.
                        # I wonder if something about TestCase instantiation order
                        # changed in pytest 8? Either way, we can't access
                        # __self__.settings under pytest 7.
                        #
                        # I am going to call this an acceptably rare bug for now,
                        # because it should only manifest if the user sets a custom
                        # database on a stateful test under pytest 7 (all non-db
                        # settings are ignored by hypofuzz).
                        settings=runTest.__self__.settings if pytest8 else None,
                    )
                    extra_kw = {"factory": StateMachineClass}
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
