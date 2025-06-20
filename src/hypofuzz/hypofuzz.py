"""Adaptive fuzzing for property-based tests using Hypothesis."""

import contextlib
import math
from collections import defaultdict
from collections.abc import Callable
from contextlib import nullcontext
from functools import partial
from random import Random
from typing import Any, Literal, Optional, Union

import pytest
from hypothesis import HealthCheck, Verbosity, settings
from hypothesis.core import (
    StateForActualGivenExecution,
    Stuff,
    process_arguments_to_given,
)
from hypothesis.database import ListenerEventT
from hypothesis.errors import StopTest
from hypothesis.internal.conjecture.data import (
    ConjectureData,
    Status,
    _Overrun,
)
from hypothesis.internal.conjecture.engine import RunIsComplete
from hypothesis.internal.escalation import current_pytest_item
from hypothesis.internal.observability import (
    InfoObservation,
    TestCaseObservation,
    with_observation_callback,
)
from hypothesis.internal.reflection import (
    function_digest,
    get_pretty_function_description,
    get_signature,
)

from hypofuzz.bayes import behaviors_per_second, softmax
from hypofuzz.collection import collect_tests
from hypofuzz.corpus import (
    get_shrinker,
)
from hypofuzz.database import (
    ChoicesT,
    DatabaseEvent,
    FailureState,
    HypofuzzDatabase,
    Observation,
    Phase,
    convert_db_key,
)
from hypofuzz.provider import HypofuzzProvider

# 1 hour
SHRINK_TIMEOUT = 60 * 60


class HitShrinkTimeoutError(Exception):
    pass


class HypofuzzStateForActualGivenExecution(StateForActualGivenExecution):
    def _should_trace(self) -> bool:
        # we're handling our own coverage collection, both for observability and
        # for failing examples (explain phase).
        return False


class FuzzTarget:
    """
    FuzzTarget is a thin wrapper around HypofuzzProvider, which also handles
    shrinking failures in a way that saves observations correctly for Hypofuzz.
    """

    @classmethod
    def from_hypothesis_test(
        cls,
        wrapped_test: Any,
        *,
        database: HypofuzzDatabase,
        extra_kw: Optional[dict[str, object]] = None,
        pytest_item: Optional[pytest.Item] = None,
    ) -> "FuzzTarget":
        _, _, stuff = process_arguments_to_given(
            wrapped_test,
            arguments=(),
            kwargs=extra_kw or {},
            given_kwargs=wrapped_test.hypothesis._given_kwargs,
            params=get_signature(wrapped_test).parameters,  # type: ignore
        )
        assert settings.default is not None
        return cls(
            test_fn=wrapped_test.hypothesis.inner_test,
            stuff=stuff,
            database=database,
            database_key=function_digest(wrapped_test.hypothesis.inner_test),
            wrapped_test=wrapped_test,
            pytest_item=pytest_item,
        )

    def __init__(
        self,
        test_fn: Callable,
        stuff: Stuff,
        *,
        database: HypofuzzDatabase,
        database_key: bytes,
        wrapped_test: Callable,
        pytest_item: Optional[pytest.Item] = None,
    ) -> None:
        self.random = Random()
        self._test_fn = test_fn
        self._stuff = stuff
        self.nodeid = getattr(
            pytest_item, "nodeid", None
        ) or get_pretty_function_description(test_fn)
        self.database_key = database_key
        self.database_key_str = convert_db_key(self.database_key, to="str")
        self.database = database
        self.state = HypofuzzStateForActualGivenExecution(  # type: ignore
            stuff,
            self._test_fn,
            settings(
                database=self.database._db,
                deadline=None,
                suppress_health_check=list(HealthCheck),
                verbosity=Verbosity.quiet,
            ),
            self.random,
            wrapped_test,
        )
        self.wrapped_test = wrapped_test
        self.pytest_item = pytest_item

        self.provider = HypofuzzProvider(None)
        self.stop_shrinking_at = math.inf

    def new_conjecture_data(
        self, *, choices: Optional[ChoicesT] = None
    ) -> ConjectureData:
        if choices is not None:
            return ConjectureData.for_choices(
                choices, provider=self.provider, random=self.random
            )
        return ConjectureData(provider=self.provider, random=self.random)

    def run_one(self) -> None:
        """Run a single input through the fuzz target, or maybe more.

        The "more" part is in cases where we discover a new behavior, and shrink
        to the minimal covering example.
        """
        data = self.new_conjecture_data()
        # seen_count = len(self.provider.corpus.branch_counts)
        self._execute_once(data, observation_callback=self.provider.on_observation)

        data.freeze()
        result = data.as_result()

        if result.status is Status.INTERESTING:
            assert not isinstance(result, _Overrun)
            # Shrink to our minimal failing example, since we'll stop after this.

            # _start_phase here is a horrible horrible hack, reporting and phase
            # logic needs to be extracted / unified somehow
            self.provider._start_phase(Phase.SHRINK)
            shrinker = get_shrinker(
                partial(self._execute_once, observation_callback=None),
                initial=result,
                predicate=lambda d: d.status is Status.INTERESTING,
                random=self.random,
                explain=True,
            )
            self.stop_shrinking_at = self.provider.elapsed_time + SHRINK_TIMEOUT
            with contextlib.suppress(HitShrinkTimeoutError, RunIsComplete):
                shrinker.shrink()

            self.provider._start_phase(Phase.FAILED)
            # re-execute the failing example under observability, for so we
            # can save the shrunk obervation.
            data = ConjectureData.for_choices(shrinker.shrink_target.choices)
            # make sure to carry over explain-phase comments
            data.slice_comments = shrinker.shrink_target.slice_comments

            observation = None

            def on_observation(
                passed_observation: Union[TestCaseObservation, InfoObservation],
            ) -> None:
                assert passed_observation.type == "test_case"
                assert passed_observation.property == self.nodeid
                nonlocal observation
                observation = passed_observation

            self._execute_once(data, observation_callback=on_observation)
            self.provider._save_report(self.provider._report)

            # move this failure from the unshrunk to the shrunk key.
            assert observation is not None
            self.database.delete_failure(
                self.database_key,
                shrinker.choices,
                state=FailureState.UNSHRUNK,
            )
            self.database.save_failure(
                self.database_key,
                shrinker.choices,
                Observation.from_hypothesis(observation),
                state=FailureState.SHRUNK,
            )

        # NOTE: this distillation logic works fine, it's just discovering new coverage
        # much more slowly than jumping directly to mutational mode.
        # if len(self.provider.corpus.branch_counts) > seen_count and not self._early_blackbox_mode:
        #     self._start_phase(Phase.DISTILL)
        #     self.corpus.distill(self._run_test_on, self.random)

    def _execute_once(
        self,
        data: ConjectureData,
        *,
        observation_callback: Union[
            Callable[[Union[InfoObservation, TestCaseObservation]], None],
            Literal["provider"],
            None,
        ] = "provider",
    ) -> None:
        # setting current_pytest_item lets us access it in HypofuzzProvider,
        # and lets observability's "property" attribute be the proper nodeid,
        # instead of just the function name
        if observation_callback == "provider":
            observation_callback = self.provider.on_observation

        with (
            (
                with_observation_callback(observation_callback)
                if observation_callback is not None
                else nullcontext()
            ),
            (
                current_pytest_item.with_value(self.pytest_item)  # type: ignore
                if self.pytest_item is not None
                else nullcontext()
            ),
        ):
            try:
                self.state._execute_once_for_engine(data)
            except StopTest:
                pass

        if self.provider.elapsed_time > self.stop_shrinking_at:
            raise HitShrinkTimeoutError

    @property
    def has_found_failure(self) -> bool:
        """If we've already found a failing example we might reprioritize."""
        corpus = self.provider.corpus
        return corpus is not None and bool(corpus.interesting_examples)


class FuzzProcess:
    """
    Manages switching between several FuzzTargets, and managing their associated
    higher-level state, like setting up and tearing down pytest fixtures.
    """

    def __init__(self, targets: list[FuzzTarget]) -> None:
        self.random = Random()
        self.targets = targets

        self.event_dispatch: dict[bytes, list[FuzzTarget]] = defaultdict(list)
        for target in targets:
            self.event_dispatch[target.database_key].append(target)

    def on_event(self, listener_event: ListenerEventT) -> None:
        event = DatabaseEvent.from_event(listener_event)
        if event is None or event.database_key not in self.event_dispatch:
            return

        for target in self.event_dispatch[event.database_key]:
            target.provider.on_event(event)

    @property
    def valid_targets(self) -> list[FuzzTarget]:
        # the targets we actually want to run/fuzz
        return [t for t in self.targets if not t.has_found_failure]

    def start(self) -> None:
        settings().database.add_listener(self.on_event)

        while True:
            if not self.valid_targets:
                break

            # choose the next target to fuzz with probability equal to the softmax
            # of its estimator. aka boltzmann exploration
            estimators = [behaviors_per_second(target) for target in self.valid_targets]
            estimators = softmax(estimators)
            # softmax might return 0.0 probability for some targets if there is
            # a substantial gap in estimator values (e.g. behaviors_per_second=1_000
            # vs behaviors_per_second=1.0). We don't expect this to happen normally,
            # but it might when our estimator state is just getting started.
            #
            # Mix in a uniform probability of 1%, so we will eventually get out of
            # such a hole.
            if self.random.random() < 0.01:
                target = self.random.choice(self.valid_targets)
            else:
                target = self.random.choices(
                    self.valid_targets, weights=estimators, k=1
                )[0]

            # TODO we should scale this n up if our estimator expects that it will
            # take a long time to discover a new behavior, to reduce the overhead
            # of switching.
            for _ in range(100):
                target.run_one()


def _fuzz(pytest_args: tuple[str, ...], nodeids: list[str]) -> None:
    """Collect and fuzz tests.

    Designed to be used inside a multiprocessing.Process started with the spawn()
    method - requires picklable arguments but works on Windows too.
    """
    tests = [t for t in collect_tests(pytest_args).fuzz_targets if t.nodeid in nodeids]
    process = FuzzProcess(tests)
    process.start()
