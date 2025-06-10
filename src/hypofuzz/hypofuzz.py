"""Adaptive fuzzing for property-based tests using Hypothesis."""

import contextlib
import itertools
import math
from collections import defaultdict
from collections.abc import Callable
from contextlib import nullcontext
from random import Random
from typing import Any, Optional, Union

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
from sortedcontainers import SortedKeyList

from hypofuzz.corpus import (
    get_shrinker,
)
from hypofuzz.database import (
    ChoicesT,
    DatabaseEvent,
    HypofuzzDatabase,
    Observation,
    Phase,
    convert_db_key,
)
from hypofuzz.provider import HypofuzzProvider


class HitShrinkTimeoutError(Exception):
    pass


class HypofuzzStateForActualGivenExecution(StateForActualGivenExecution):
    def _should_trace(self) -> bool:
        # we're handling our own coverage collection, both for observability and
        # for failing examples (explain phase).
        return False


class FuzzProcess:
    """
    Thin wrapper around HypofuzzProvider, which also handles shrinking failures
    in a way that saves observations correctly for Hypofuzz.
    """

    @classmethod
    def from_hypothesis_test(
        cls,
        wrapped_test: Any,
        *,
        database: HypofuzzDatabase,
        extra_kw: Optional[dict[str, object]] = None,
        pytest_item: Optional[pytest.Item] = None,
    ) -> "FuzzProcess":
        """Return a FuzzProcess for an @given-decorated test function."""
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
        random_seed: int = 0,
        database: HypofuzzDatabase,
        database_key: bytes,
        wrapped_test: Callable,
        pytest_item: Optional[pytest.Item] = None,
    ) -> None:
        """Construct a FuzzProcess from specific arguments."""
        self.random = Random(random_seed)
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

        The "more" part is in cases where we discover new coverage, and shrink
        to the minimal covering example.
        """
        data = self.new_conjecture_data()
        # seen_count = len(self.provider.corpus.branch_counts)
        self._execute_once(data)

        data.freeze()
        result = data.as_result()

        if result.status is Status.INTERESTING:
            assert not isinstance(result, _Overrun)
            # Shrink to our minimal failing example, since we'll stop after this.
            # horrible horrible hack, reporting and phase logic needs to be
            # extracted / unified somehow
            self.provider._start_phase(Phase.SHRINK)
            shrinker = get_shrinker(
                self._execute_once_for_shrinker,
                initial=result,
                predicate=lambda d: d.status is Status.INTERESTING,
                random=self.random,
                explain=True,
            )
            self.stop_shrinking_at = self.provider.elapsed_time + 300
            with contextlib.suppress(HitShrinkTimeoutError, RunIsComplete):
                shrinker.shrink()

            self.provider._start_phase(Phase.FAILED)
            # we re-execute the failing example under observability, for
            # db.save_failure_observation.
            data = ConjectureData.for_choices(shrinker.shrink_target.choices)
            # make sure to carry over explain-phase comments
            data.slice_comments = shrinker.shrink_target.slice_comments

            observation = None

            def on_observation(
                passed_observation: Union[TestCaseObservation, InfoObservation],
            ) -> None:
                assert passed_observation.type == "test_case"
                nonlocal observation
                observation = passed_observation

            with with_observation_callback(on_observation):
                try:
                    self.state._execute_once_for_engine(data)
                except StopTest:
                    pass

            self.provider._save_report(self.provider._report)
            # move this failure from the unshrunk to the shrunk key.
            self.database.save_failure(self.database_key, shrinker.choices, shrunk=True)
            self.database.delete_failure(
                self.database_key, shrinker.choices, shrunk=False
            )
            assert observation is not None
            self.database.save_failure_observation(
                self.database_key,
                shrinker.choices,
                Observation.from_hypothesis(observation),
            )

        # NOTE: this distillation logic works fine, it's just discovering new coverage
        # much more slowly than jumping directly to mutational mode.
        # if len(self.provider.corpus.branch_counts) > seen_count and not self._early_blackbox_mode:
        #     self._start_phase(Phase.DISTILL)
        #     self.corpus.distill(self._run_test_on, self.random)

    def _execute_once(self, data: ConjectureData) -> None:
        assert data.provider is self.provider
        # setting current_pytest_item lets use access it in HypofuzzProvider,
        # and lets observability's "property" attribute be the proper nodeid,
        # instead of just the function name
        with (
            with_observation_callback(self.provider.on_observation),
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

    def _execute_once_for_shrinker(self, data: ConjectureData) -> None:
        assert not isinstance(data.provider, HypofuzzProvider)
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


def fuzz_several(targets: list[FuzzProcess], random_seed: Optional[int] = None) -> None:
    """Take N fuzz targets and run them all."""
    random = Random(random_seed)
    targets: SortedKeyList[FuzzProcess, int] = SortedKeyList(
        targets, lambda p: p.provider.since_new_branch
    )

    # Loop forever: at each timestep, we choose a target using an epsilon-greedy
    # strategy for simplicity (TODO: improve this later) and run it once.
    # TODO: make this aware of test runtime, so it adapts for behaviors-per-second
    #       rather than behaviors-per-input.

    dispatch: dict[bytes, list[FuzzProcess]] = defaultdict(list)
    for target in targets:
        dispatch[target.database_key].append(target)

    def on_event(listener_event: ListenerEventT) -> None:
        event = DatabaseEvent.from_event(listener_event)
        if event is None or event.database_key not in dispatch:
            return

        for target in dispatch[event.database_key]:
            target.provider.on_event(event)

    settings().database.add_listener(on_event)

    resort = False
    for count in itertools.count():
        if count % 20 == 0:
            resort = True
            i = random.randrange(len(targets))
        else:
            i = 0
        target = targets[i]
        target.run_one()
        if target.has_found_failure:
            print(f"found failing example for {target.nodeid}")
            targets.pop(i)

        if targets and (
            resort
            or (len(targets) > 1 and targets.key(targets[0]) > targets.key(targets[1]))
        ):
            # pay our log-n cost to keep the list sorted
            targets.add(targets.pop(0))

        if not targets:
            return
    raise NotImplementedError("unreachable")
