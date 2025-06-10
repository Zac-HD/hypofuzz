"""CLI and Python API for the fuzzer."""

import io
import sys
import traceback
from collections.abc import Iterable
from contextlib import redirect_stdout
from dataclasses import dataclass
from inspect import signature
from typing import TYPE_CHECKING, Any, Optional, get_type_hints

import pytest
from _pytest.nodes import Item, Node
from _pytest.skipping import evaluate_condition
from hypothesis import settings
from hypothesis.database import BackgroundWriteDatabase
from hypothesis.stateful import get_state_machine_test
from packaging import version

if TYPE_CHECKING:
    # We have to defer imports to within functions here, because this module
    # is a Hypothesis entry point and is thus imported earlier than the others.
    from hypofuzz.hypofuzz import FuzzProcess

pytest8 = version.parse(pytest.__version__) >= version.parse("8.0.0")


def has_true_skipif(item: Item) -> tuple[bool, Optional[str]]:
    # multiple @skipif decorators are treated as an OR.
    for mark in item.iter_markers("skipif"):
        result, reason = evaluate_condition(item, mark, condition=mark.args[0])
        if result:
            return (True, reason)
    return (False, None)


@dataclass
class CollectionResult:
    fuzz_targets: list["FuzzProcess"]
    not_collected: dict[str, dict[str, Any]]


class _ItemsCollector:
    """A pytest plugin which grabs all the fuzzable tests at the end of collection."""

    def __init__(self) -> None:
        self.fuzz_targets: list[FuzzProcess] = []
        self.not_collected: dict[str, dict[str, Any]] = {}

    def _skip_because(
        self, status_reason: str, nodeid: str, kwargs: Optional[dict[str, Any]] = None
    ) -> None:
        self.not_collected[nodeid] = {
            "status_reason": status_reason,
            **(kwargs or {}),
        }

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        from hypofuzz.database import HypofuzzDatabase
        from hypofuzz.hypofuzz import FuzzProcess

        # We guarantee (and enforce here at collection-time) that all tests
        # collected by hypofuzz use the same database, and that that database is
        # the same as the default settings().database at the time of collection.
        # This lets us share a single hypofuzz_db across all FuzzProcess classes,
        # which is nice because we don't want to create a thread for every fuzz
        # process to handle the background writes.
        db = settings().database
        if not isinstance(db, BackgroundWriteDatabase):
            db = BackgroundWriteDatabase(db)
        hypofuzz_db = HypofuzzDatabase(db)

        for item in session.items:
            if not isinstance(item, pytest.Function):
                self._skip_because("not_a_function", item.nodeid)
                continue
            # we're only noting the reason for the first skip and skipifs for
            # now, not all of them. Be careful that this matches pytest semantics;
            # pytest might not evaluate conditions beyond the first true one,
            # which could cause side effects.
            if skips := list(item.iter_markers("skip")):
                # reason is in either args or kwargs depending on how it was
                # passed to the mark. all 3 are valid:
                # * @pytest.mark.skip()
                # * @pytest.mark.skip("myreason")
                # * @pytest.mark.skip(reason="myreason")
                reason = (
                    skips[0].args[0] if skips[0].args else skips[0].kwargs.get("reason")
                )
                self._skip_because("skip", item.nodeid, {"reason": reason})
                continue
            (true_skipif, skipif_reason) = has_true_skipif(item)
            if true_skipif:
                self._skip_because("skipif", item.nodeid, {"reason": skipif_reason})
                continue

            # skip xfail tests for now. We could in theory fuzz strict xfail
            # tests for an input which does not cause a failure.
            if list(item.iter_markers("xfail")):
                self._skip_because("xfail", item.nodeid)
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
                self._skip_because("fixture", item.nodeid, {"fixtures": names})
                continue

            if (
                test_database := getattr(
                    item.obj, "_hypothesis_internal_use_settings", settings()
                ).database
            ) != settings().database:
                self._skip_because(
                    "differing_database",
                    item.nodeid,
                    {
                        "default_database": settings().database,
                        "test_database": test_database,
                    },
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
                    # our pytest plugin would normally add this. Necessary to
                    # distinguish pytest.mark.parametrize.
                    item.obj.hypothesis.inner_test._hypothesis_internal_add_digest = (
                        item.nodeid.encode()
                    )
                    target = item.obj
                fuzz = FuzzProcess.from_hypothesis_test(
                    target, database=hypofuzz_db, extra_kw=extra_kw, pytest_item=item
                )
            except Exception as e:
                self._skip_because(
                    "error",
                    item.nodeid,
                    {"traceback": "".join(traceback.format_exception(e))},
                )
            else:
                self.fuzz_targets.append(fuzz)


def _get_hypothesis_tests_with_pytest(
    args: Iterable[str], *, debug: bool = False
) -> CollectionResult:
    """Find the hypothesis-only test functions run by pytest.

    This basically uses `pytest --collect-only -m hypothesis $args`.
    """
    args = list(args)
    if debug:
        args.append("-s")
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
    elif debug or not collector.fuzz_targets:
        print("debug:" if debug else "no fuzz targets found:")
        print(out.getvalue())
        print("The following tests were not collected:")
        for nodeid, reason in collector.not_collected.items():
            print(f"{nodeid} (because: {reason})")

    return CollectionResult(
        fuzz_targets=collector.fuzz_targets, not_collected=collector.not_collected
    )


def _fuzz_several(pytest_args: tuple[str, ...], nodeids: list[str]) -> None:
    """Collect and fuzz tests.

    Designed to be used inside a multiprocessing.Process started with the spawn()
    method - requires picklable arguments but works on Windows too.
    """
    # Import within the function to break an import cycle when used as an entry point.
    from hypofuzz.hypofuzz import fuzz_several

    tests = [
        t
        for t in _get_hypothesis_tests_with_pytest(pytest_args).fuzz_targets
        if t.nodeid in nodeids
    ]
    fuzz_several(tests)
