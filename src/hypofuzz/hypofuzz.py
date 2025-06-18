"""Adaptive fuzzing for property-based tests using Hypothesis."""

import contextlib
import math
import time
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from contextlib import nullcontext
from functools import partial
from multiprocessing import Manager, Process
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

from hypofuzz.bayes import (
    BehaviorRates,
    CurrentWorker,
    DistributeNodesTarget,
    bandit_weights,
    distribute_nodes,
    e_target_rates,
    e_worker_lifetime,
)
from hypofuzz.collection import collect_tests
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
                self.database_key, shrinker.choices, observation=None, shrunk=False
            )
            self.database.save_failure(
                self.database_key,
                shrinker.choices,
                Observation.from_hypothesis(observation),
                shrunk=True,
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


class FuzzWorker:
    """
    Manages switching between several FuzzTargets, and also manages their
    associated higher-level state, like setting up and tearing down pytest
    fixtures.
    """

    def __init__(
        self,
        *,
        pytest_args: Sequence[str],
        shared_state: Mapping,
    ) -> None:
        self.pytest_args = pytest_args
        self.shared_state = shared_state

        self.random = Random()
        # the current pool of node ids this process has available to fuzz. This
        # might be adjusted by FuzzWorkerHub via `shared_state` as estimators
        # update and nodeids are rebalanced across workers.
        self.nodeids: Sequence[str] = []
        # The list of all collected fuzz targets. We collect this at the beginning
        # by running a pytest collection step.
        #
        # This is never modified or copied from after the initial collection.
        # When we need an actual target to fuzz, we create a new FuzzTarget
        # instance to put into self.targets.
        self.collected_fuzz_targets: list[FuzzTarget] = []
        # the current pool of active targets this worker can fuzz immediately.
        # This is the subset of `nodeids` which this worker has chosen to start
        # up.
        self.targets: list[FuzzTarget] = []
        # targets which we have previously started fuzzing, but have since been
        # told to drop by the hub. We keep the fuzz target in memory because we
        # might be told by the hub to pick this target up again in the future.
        #
        # When starting, dropping, and starting a target again, we cannot violate
        # the linear reports invariant that we do not write reports from the same
        # worker, on the same target, at two different fuzz campaigns for that
        # target. Once a worker starts fuzzing a target, it cannot restart fuzzing
        # that target from scratch without changing its uuid or wiping the previous
        # campaign, neither of which are feasible.
        self.dropped_targets: list[FuzzTarget] = []
        self.event_dispatch: dict[bytes, list[FuzzTarget]] = defaultdict(list)

    def add_target(self, nodeid: str) -> None:
        # if this target was previously dropped, move it from `dropped_targets`
        # to `targets`, without creating a new FuzzTarget.
        dropped_targets = [t for t in self.dropped_targets if t.nodeid == nodeid]
        if dropped_targets:
            target = dropped_targets[0]
            self.targets.append(target)
            self.dropped_targets.remove(target)
            return

        targets = [t for t in self.collected_fuzz_targets if t.nodeid == nodeid]
        assert len(targets) == 1
        target = targets[0]

        # create a new FuzzTarget to put into self.targets, to avoid modifying
        # collected_fuzz_targets at all
        target = FuzzTarget(
            test_fn=target._test_fn,
            stuff=target._stuff,
            database=target.database,
            database_key=target.database_key,
            wrapped_test=target.wrapped_test,
            pytest_item=target.pytest_item,
        )
        self.targets.append(target)
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

    def _maybe_add_targets(self) -> None:
        # consider whether it's worthwhile to add more targets
        active_nodeids = {target.nodeid for target in self.targets}
        candidates = [nodeid for nodeid in self.nodeids if nodeid not in active_nodeids]
        # TODO actually defer starting up targets here, based on worker lifetime
        # and startup cost estimators here
        for nodeid in candidates:
            self.add_target(nodeid)

    def _update_targets(self, nodeids: Sequence[str]) -> None:
        # Update our nodeids and targets with new directives from the hub.
        # * Nodes in both nodeids and self.targets are kept as-is
        # * Nodes in nodeids but not self.targets are added to our available
        #   nodeids, to potentially be added as targets later (by _maybe_add_targets)
        # * Nodes in self.targets but not nodeids are evicted from our targets.
        #   These are nodes that the hub has decided are better to hand off to
        #   another process.
        for target in self.targets.copy():
            if target.nodeid not in nodeids:
                self.targets.remove(target)
                self.dropped_targets.append(target)
                # we intentionally do not remove our event_dispatch listener
                # here, because if we are ever told to pick up this dropped target
                # again in the future, we still want its corpus and failure replay
                # to be up to date from other workers.

        self.nodeids = nodeids

    def start(self) -> None:
        self.worker_start = time.perf_counter()
        self.collected_fuzz_targets = collect_tests(self.pytest_args).fuzz_targets
        settings().database.add_listener(self.on_event)

        while True:
            self._update_targets(self.shared_state["hub_state"]["nodeids"])
            self._maybe_add_targets()

            if not self.valid_targets:
                break

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
                behaviors_rates = [
                    e_target_rates(target) for target in self.valid_targets
                ]
                weights = bandit_weights(behaviors_rates)
                target = self.random.choices(self.valid_targets, weights=weights, k=1)[
                    0
                ]

            # TODO we should scale this n up if our estimator expects that it will
            # take a long time to discover a new behavior, to reduce the overhead
            # of switching targets.
            for _ in range(100):
                target.run_one()

            # give the hub an up-to-date estimator state
            current_lifetime = time.perf_counter() - self.worker_start
            worker_state = self.shared_state["worker_state"]
            worker_state["current_lifetime"] = current_lifetime
            worker_state["expected_lifetime"] = e_worker_lifetime(current_lifetime)
            worker_state["nodeids"][target.nodeid] = {
                "behavior_rates": e_target_rates(target),
            }


class FuzzWorkerHub:
    def __init__(
        self,
        *,
        nodeids: Sequence[str],
        pytest_args: Sequence[str],
        n_processes: int,
    ) -> None:
        self.nodeids = nodeids
        self.pytest_args = pytest_args
        self.n_processes = n_processes

        self.shared_states: list[Mapping] = []

    def start(self) -> None:
        processes: list[Process] = []

        with Manager() as manager:
            for _ in range(self.n_processes):
                shared_state = manager.dict()
                shared_state["hub_state"] = manager.dict()
                shared_state["worker_state"] = manager.dict()
                shared_state["worker_state"]["nodeids"] = manager.dict()
                shared_state["worker_state"]["current_lifetime"] = 0.0
                shared_state["worker_state"]["expected_lifetime"] = 0.0

                process = Process(
                    target=_start_worker,
                    kwargs={
                        "pytest_args": self.pytest_args,
                        "shared_state": shared_state,
                    },
                )
                processes.append(process)
                self.shared_states.append(shared_state)

            # rebalance once at the start to put the initial node assignments
            # in the shared state
            self._rebalance()
            for process in processes:
                process.start()

            while True:
                # rebalance automatically on an interval.
                # We may want to check some condition more frequently than this,
                # like "a process has no more nodes" (due to e.g. finding a
                # failure). So we rebalance either once every n seconds, or whenever
                # some worker needs a rebalancing.
                time.sleep(60)
                # if all our workers have exited, we should exit as well
                if all(not process.is_alive() for process in processes):
                    break

                self._rebalance()

    def _rebalance(self) -> None:
        # rebalance the assignment of nodeids to workers, according to the
        # up-to-date estimators from our workers.

        assert len(self.shared_states) == self.n_processes
        current_workers = [
            CurrentWorker(
                nodeids=state["worker_state"]["nodeids"].keys(),
                e_lifetime=state["worker_state"]["expected_lifetime"],
            )
            for state in self.shared_states
        ]

        # fill with default estimators, for the first-time startup
        # nodeid: (worker_lifetime, rates)
        targets = {
            nodeid: (0.0, BehaviorRates(per_second=1.0, per_input=1.0))
            for nodeid in self.nodeids
        }
        for state in self.shared_states:
            worker_state = state["worker_state"]
            worker_lifetime = worker_state["current_lifetime"]
            for nodeid, rates in worker_state["nodeids"].items():
                if nodeid not in targets:
                    targets[nodeid] = (worker_lifetime, rates)

                # if the nodeid already exists, but we have a better estimator
                # for it, replace it
                if worker_lifetime > targets[nodeid][0]:
                    targets[nodeid] = (worker_lifetime, rates)

        # TODO estimate startup time of this target
        # ("number of corpus elements" * "average input runtime" probably?)
        targets = [
            DistributeNodesTarget(nodeid=nodeid, rates=rates, e_startup_time=0)
            for nodeid, (_lifetime, rates) in targets.items()
        ]
        partitions = distribute_nodes(
            targets,
            n=self.n_processes,
            current_workers=current_workers,
        )

        # communicate the worker's new nodeids back to the worker.
        #
        # the iteration order of the partitions returned by distribute_nodes is
        # the same as the iteration order of current_workers
        for state, nodeids in zip(self.shared_states, partitions):
            state["hub_state"]["nodeids"] = nodeids


def _start_worker(
    pytest_args: Sequence[str],
    shared_state: Mapping,
) -> None:
    """Collect and fuzz tests.

    Designed to be used inside a multiprocessing.Process started with the spawn()
    method - requires picklable arguments but works on Windows too.
    """
    process = FuzzWorker(pytest_args=pytest_args, shared_state=shared_state)
    process.start()
