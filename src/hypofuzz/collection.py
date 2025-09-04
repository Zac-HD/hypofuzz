"""CLI and Python API for the fuzzer."""

import io
import sys
import traceback
from collections.abc import Iterable
from contextlib import redirect_stdout
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from hypothesis import HealthCheck

import pytest
from _pytest.nodes import Item
from _pytest.skipping import evaluate_condition
from hypothesis import Phase, settings
from hypothesis.database import BackgroundWriteDatabase
from hypothesis.stateful import get_state_machine_test
from packaging import version

if TYPE_CHECKING:
    # We have to defer imports to within functions here, because this module
    # is a Hypothesis entry point and is thus imported earlier than the others.
    from hypofuzz.hypofuzz import FuzzTarget

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
    fuzz_targets: list["FuzzTarget"]
    not_collected: dict[str, dict[str, Any]]


class _ItemsCollector:
    """A pytest plugin which grabs all the fuzzable tests at the end of collection."""

    def __init__(self) -> None:
        self.fuzz_targets: list[FuzzTarget] = []
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
        from hypofuzz.hypofuzz import FuzzTarget

        # We guarantee (and enforce here at collection-time) that all tests
        # collected by hypofuzz use the same database, and that that database is
        # the same as the default settings().database at the time of collection.
        # This lets us share a single hypofuzz_db across all FuzzTarget classes,
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

            # from @pytest.mark.parametrize. Pytest gives us the params and their
            # values directly, so we can pass them as extra kwargs to FuzzTarget.
            extra_kwargs = item.callspec.params if hasattr(item, "callspec") else {}

            test_settings = getattr(
                item.obj, "_hypothesis_internal_use_settings", settings()
            )

            # derandomize=True implies database=None, so this will be skipped by our
            # differing_database check below anyway, but we can give a less confusing
            # skip reason by checking for derandomize explicitly.
            if test_settings.derandomize:
                self._skip_because("sets_derandomize", item.nodeid)
                continue

            if (test_database := test_settings.database) != settings().database:
                self._skip_because(
                    "differing_database",
                    item.nodeid,
                    {
                        "default_database": settings().database,
                        "test_database": test_database,
                    },
                )
                continue

            # if this test has been told not to generate inputs, don't fuzz it.
            if Phase.generate not in test_settings.phases:
                self._skip_because(
                    "no_generate_phase", item.nodeid, {"phases": test_settings.phases}
                )
                continue

            # nesting @given has undefined (for now) observability semantics,
            # for example for PrimitiveProvider.on_observation. Skip until we
            # can support it.
            if HealthCheck.nested_given in test_settings.suppress_health_check:
                self._skip_because(
                    "nested_given",
                    item.nodeid,
                    {"suppress_health_check": test_settings.suppress_health_check},
                )
                continue

            # Wrap it up in a FuzzTarget and we're done!
            try:
                if hasattr(item.obj, "_hypothesis_state_machine_class"):
                    assert (
                        extra_kwargs == {}
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
                else:
                    # our pytest plugin would normally add this. Necessary to
                    # distinguish pytest.mark.parametrize.
                    item.obj.hypothesis.inner_test._hypothesis_internal_add_digest = (
                        item.nodeid.encode()
                    )
                    target = item.obj

                if getattr(target, "__self__", None) is not None:
                    # Hypothesis internals (like process_arguments_to_given) don't
                    # expect to work with bound methods, because @given is applied
                    # at the point of it still being a plain function with a `self`
                    # argument.
                    #
                    # At the point of pytest collection, `target` might be a bound
                    # method, though. (I believe iff isinstance(item, TestCaseFunction),
                    # but I don't want to assert that here in case I'm wrong).
                    #
                    # So pass on the function, not the bound method - FuzzTarget will
                    # take care of inserting the `self` arg instance from `item` when
                    # constructing StateForActualGivenExecution.
                    target = target.__func__

                fuzz = FuzzTarget.from_hypothesis_test(
                    target,
                    database=hypofuzz_db,
                    extra_kwargs=extra_kwargs,
                    pytest_item=item,
                )
            except Exception as e:
                self._skip_because(
                    "error",
                    item.nodeid,
                    {"traceback": "".join(traceback.format_exception(e))},
                )
            else:
                self.fuzz_targets.append(fuzz)


def collect_tests(args: Iterable[str], *, debug: bool = False) -> CollectionResult:
    """Find the hypothesis-only test functions run by pytest.

    This basically uses `pytest --collect-only -m hypothesis $args`.
    """
    args = list(args)
    if debug:
        args.append("-s")
    collector = _ItemsCollector()
    out = io.StringIO()
    with redirect_stdout(out):
        exit_code = pytest.main(
            args=[
                "--collect-only",
                "-m=hypothesis",
                "--pythonwarnings=ignore::pytest.PytestAssertRewriteWarning",
                *args,
            ],
            plugins=[collector],
        )
    if exit_code:
        print(out.getvalue())
        if exit_code == 5:
            # nice error message for the common case
            print("Exiting because pytest didn't collect any tests")
        else:
            print(f"Exiting because pytest returned exit code {exit_code}")
        sys.exit(exit_code)
    elif debug or not collector.fuzz_targets:
        print("debug:" if debug else "no Hypothesis tests found:")
        print(out.getvalue())
        print("The following tests were not collected:")
        for nodeid, reason in collector.not_collected.items():
            print(f"{nodeid} (because: {reason})")

    return CollectionResult(
        fuzz_targets=collector.fuzz_targets, not_collected=collector.not_collected
    )
