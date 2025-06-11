"""Adaptive fuzzing for property-based tests using Hypothesis."""

import contextlib
import inspect
import itertools
import math
import os
import platform
import socket
import subprocess
import sys
import time
from collections import defaultdict
from collections.abc import Callable, Generator
from contextlib import contextmanager, nullcontext
from enum import IntEnum
from functools import lru_cache
from pathlib import Path
from random import Random
from typing import Any, Optional, Union
from uuid import uuid4

import hypothesis
import pytest
from hypothesis import HealthCheck, settings
from hypothesis.core import (
    StateForActualGivenExecution,
    Stuff,
    process_arguments_to_given,
)
from hypothesis.database import ListenerEventT
from hypothesis.errors import StopTest
from hypothesis.internal.conjecture.choice import ChoiceT, ChoiceTemplate, choices_size
from hypothesis.internal.conjecture.data import (
    ConjectureData,
    ConjectureResult,
    Status,
    _Overrun,
)
from hypothesis.internal.conjecture.engine import RunIsComplete
from hypothesis.internal.escalation import current_pytest_item
from hypothesis.internal.observability import (
    TESTCASE_CALLBACKS,
    Observation as HypothesisObservation,
)
from hypothesis.internal.reflection import (
    function_digest,
    get_pretty_function_description,
    get_signature,
)
from hypothesis.reporting import with_reporter
from sortedcontainers import SortedKeyList, SortedList

import hypofuzz
from hypofuzz.corpus import (
    Choices,
    Corpus,
    get_shrinker,
)
from hypofuzz.coverage import CoverageCollector
from hypofuzz.database import (
    ChoicesT,
    DatabaseEvent,
    DatabaseEventKey,
    HypofuzzDatabase,
    Observation,
    Phase,
    Report,
    StatusCounts,
    WorkerIdentity,
    convert_db_key,
    test_keys_key,
)
from hypofuzz.mutator import BlackBoxMutator, CrossOverMutator
from hypofuzz.provider import HypofuzzProvider
from hypofuzz.utils import Value, lerp

process_uuid = uuid4().hex

assert time.get_clock_info("perf_counter").monotonic, (
    "HypoFuzz relies on perf_counter being monotonic. This is guaranteed on "
    "CPython. Please open an issue if you hit this assertion."
)


class HitShrinkTimeoutError(Exception):
    pass


class HypofuzzStateForActualGivenExecution(StateForActualGivenExecution):
    def _should_trace(self) -> bool:
        # we're handling our own coverage collection, both for observability and
        # for failing examples (explain phase).
        return False


# like choices_size, but handles ChoiceTemplate
def _choices_size(choices: tuple[Union[ChoiceT, ChoiceTemplate], ...]) -> int:
    return sum(
        1 if isinstance(choice, ChoiceTemplate) else choices_size([choice])
        for choice in choices
    )


class ReplayFailurePriority(IntEnum):
    SHRUNK = 0
    UNSHRUNK = 1


class FuzzProcess:
    """Maintain all the state associated with fuzzing a single target.

    This includes:

        - the coverage map and associated inputs
        - references to Hypothesis' database for this test (for failure replay)
        - a "run one" method, and an estimate of the value of running one input
        - checkpointing tools so we can crash and restart without losing progess

    etc.  The fuzz controller will then operate on a collection of these objects.
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
        nodeid: Optional[str] = None,
        database: HypofuzzDatabase,
        database_key: bytes,
        wrapped_test: Callable,
        pytest_item: Optional[pytest.Item] = None,
    ) -> None:
        """Construct a FuzzProcess from specific arguments."""
        # The actual fuzzer implementation
        self.random = Random(random_seed)
        self._test_fn = test_fn
        self._stuff = stuff
        self.nodeid = getattr(
            pytest_item, "nodeid", None
        ) or get_pretty_function_description(test_fn)
        self.database_key = database_key
        self.database_key_str = convert_db_key(self.database_key, to="str")
        self.db = database
        self.state = HypofuzzStateForActualGivenExecution(  # type: ignore
            stuff,
            self._test_fn,
            settings(
                database=None, deadline=None, suppress_health_check=list(HealthCheck)
            ),
            self.random,
            wrapped_test,
        )
        self.pytest_item = pytest_item

        # The corpus is responsible for managing all seed state, including saving
        # novel seeds to the database.  This includes tracking how often each branch
        # has been hit, minimal covering examples, and so on.
        self.corpus = Corpus(database, database_key)
        self._mutator_blackbox = BlackBoxMutator(self.corpus, self.random)
        self._mutator_crossover = CrossOverMutator(self.corpus, self.random)

        # Set up the basic data that we'll track while fuzzing
        self.ninputs = 0
        self.elapsed_time = 0.0
        self.stop_shrinking_at = float("inf")
        self.since_new_branch = 0
        self.status_counts = StatusCounts()
        self.phase: Optional[Phase] = None
        self._replay_queue: SortedList[tuple[Union[ChoiceT, ChoiceTemplate], ...]] = (
            SortedList(key=_choices_size)
        )
        self._failure_queue: SortedList[
            tuple[ReplayFailurePriority, tuple[ChoicesT, Observation]]
        ] = SortedList(key=lambda x: (x[0], choices_size(x[1][0])))
        # After replay, we stay in blackbox mode for a while, until we've generated
        # 1000 consecutive examples without new coverage, and then switch to mutation.
        self._early_blackbox_mode = True
        self._last_report: Report | None = None
        self._last_saved_report_at = -math.inf

        # Track observability data
        self._last_observed = -math.inf

        self.worker_identity = worker_identity(
            in_directory=Path(inspect.getfile(self._test_fn)).parent
        )

    def startup(self) -> None:
        """Set up initial state and prepare to replay the saved behaviour."""
        # Report that we've started this fuzz target
        self.db.save(test_keys_key, self.database_key)
        # save the worker identity once at startup
        self.db.save_worker_identity(self.database_key, self.worker_identity)
        # restore our saved minimal covering corpus, as well as any failures to
        # replay.
        self._replay_queue.update(self.db.fetch_corpus(self.database_key))
        if not self._replay_queue:
            # if no worker has ever worked on this test before, save an initial
            # GENERATE report, so the graph displays a point at (0, 0).
            # This is a bit of a hack. It might be better to do this in the
            # dashboard plotting code instead, by adding a virtual point at (0, 0).
            self.phase = Phase.GENERATE
            self._save_report(self._report)
            self.phase = None

        self._replay_queue.add((ChoiceTemplate(type="simplest", count=None),))
        for shrunk in [True, False]:
            priority = (
                ReplayFailurePriority.SHRUNK
                if shrunk
                else ReplayFailurePriority.UNSHRUNK
            )
            for choices in self.db.fetch_failures(self.database_key, shrunk=shrunk):
                observation = self.db.fetch_failure_observation(
                    self.database_key, choices
                )
                if observation is None:
                    continue
                self._failure_queue.add((priority, (choices, observation)))

    def on_event(self, event: DatabaseEvent) -> None:
        # Some worker has found a new covering corpus element. Replay it in
        # this worker.
        if event.type == "save":
            if event.key is DatabaseEventKey.CORPUS:
                # the worker which saved this choice sequence might have been *us*,
                # or we might simply already have this choice sequence in our
                # corpus.
                if Choices(event.value) in self.corpus.corpus:
                    return
                self._replay_queue.add(event.value)
            # (should we also replay failures found by other workers? we may not
            # want to stop early, since we could still find a different failure.
            # but I guess the same logic would apply to the worker which found the
            # failure..)

    def _start_phase(self, phase: Phase) -> None:
        if phase is self.phase:
            return
        if self.phase is not None:
            # don't save a report the very first time we start a phase
            self._save_report(self._report)
        self.phase = phase

    def generate_data(self) -> ConjectureData:
        """Generate a test prefix by mutating previous examples.

        This is going to be the method to override when experimenting with
        alternative fuzzing techniques.

            - for unguided fuzzing, return an empty b'' and the random postfix
              generation in ConjectureData will do the rest.
            - for coverage-guided fuzzing, mutate or splice together known inputs.

        This version is terrible, but any coverage guidance at all is enough to help...
        """
        # Start by replaying any previous failures which we've retrieved from the
        # database.  This is useful to recover state at startup, or to share
        # progress made in other processes.
        while self._replay_queue:
            # we checked if we had this choice sequence when we put it into the
            # replay_queue on on_event, but we check again here, since we might have
            # executed it in the interim.
            choices = self._replay_queue.pop()

            # Choices doesn't handle ChoiceTemplate
            if (
                all(not isinstance(choice, ChoiceTemplate) for choice in choices)
                and Choices(choices) in self.corpus.corpus  # type: ignore
            ):
                continue

            self._start_phase(Phase.REPLAY)
            return ConjectureData.for_choices(choices)

        self._start_phase(Phase.GENERATE)
        # TODO: currently hard-coding a particular mutator; we want to do MOpt-style
        # adaptive weighting of all the different mutators we could use.
        # For now though, we'll just use a hardcoded swapover point
        if self._early_blackbox_mode or self.random.random() < 0.05:
            choices = self._mutator_blackbox.generate_choices()
        else:
            choices = self._mutator_crossover.generate_choices()
        return ConjectureData(
            provider=HypofuzzProvider,
            provider_kw={"choices": choices},
            random=self.random,
        )

    def run_one(self) -> None:
        """Run a single input through the fuzz target, or maybe more.

        The "more" part is in cases where we discover new coverage, and shrink
        to the minimal covering example.
        """
        if self._failure_queue:
            self._start_phase(Phase.REPLAY)
            (_priority, (choices, failure_obs)) = self._failure_queue.pop()
            data = ConjectureData.for_choices(choices)
            result = self._run_test_on(data)
            if result.status is not Status.INTERESTING:
                # this failure didn't reproduce. It's either been fixed, is flaky,
                # or is specific to the worker's environment (e.g. only fails on
                # python 3.11, while this worker is on python 3.12).
                # In any case, remove it from the db.
                #
                # We know whether this failure was shrunk or not as of when we
                # took it out of the db (via _priority). But I'm not confident that
                # it's not possible for another worker to move the same choice
                # sequence from unshrunk to shrunk - and failures are rare +
                # deletions cheap. Just try deleting from both.
                self.db.delete_failure(self.database_key, choices, shrunk=True)
                self.db.delete_failure(self.database_key, choices, shrunk=False)
                self.db.delete_failure_observation(
                    self.database_key, choices, failure_obs
                )
        else:
            result = self._run_test_on(self.generate_data())

        # seen_count = len(self.corpus.branch_counts)
        if result.status is Status.INTERESTING:
            assert not isinstance(result, _Overrun)
            # Shrink to our minimal failing example, since we'll stop after this.
            self._start_phase(Phase.SHRINK)
            shrinker = get_shrinker(
                self._run_test_on,  # type: ignore
                initial=result,
                predicate=lambda d: d.status is Status.INTERESTING,
                random=self.random,
                explain=True,
            )
            self.stop_shrinking_at = self.elapsed_time + 300
            with contextlib.suppress(HitShrinkTimeoutError, RunIsComplete):
                shrinker.shrink()
            self._start_phase(Phase.FAILED)

            # we re-execute the failing example under observability. In practice
            # the shrinker was already running under observability via _run_test_on,
            # but threading that result through to here is tricky.
            data = ConjectureData.for_choices(shrinker.shrink_target.choices)
            # make sure to carry over explain-phase comments
            data.slice_comments = shrinker.shrink_target.slice_comments
            with self.observe() as observation:
                try:
                    self.state._execute_once_for_engine(data)
                except StopTest:
                    pass

            self._save_report(self._report)
            # move this failure from the unshrunk to the shrunk key.
            self.db.save_failure(self.database_key, shrinker.choices, shrunk=True)
            self.db.delete_failure(self.database_key, shrinker.choices, shrunk=False)
            assert observation.value is not None
            self.db.save_failure_observation(
                self.database_key, shrinker.choices, observation.value
            )

        # Consider switching out of blackbox mode.
        if self.since_new_branch >= 1000 and not self._replay_queue:
            self._early_blackbox_mode = False

        # NOTE: this distillation logic works fine, it's just discovering new coverage
        # much more slowly than jumping directly to mutational mode.
        # if len(self.corpus.branch_counts) > seen_count and not self._early_blackbox_mode:
        #     self._start_phase(Phase.DISTILL)
        #     self.corpus.distill(self._run_test_on, self.random)

    def _run_test_on(
        self,
        data: ConjectureData,
        *,
        collector: Optional[contextlib.AbstractContextManager] = None,
    ) -> Union[ConjectureResult, _Overrun]:
        """Run the test_fn on a given data, in a way a Shrinker can handle.

        In normal operation, it's called via run_one (above), but we might also
        delegate to the shrinker to find minimal covering examples.
        """
        start = time.perf_counter()
        self.ninputs += 1
        collector = collector or CoverageCollector()
        reports: list[object] = []
        try:
            with (
                with_reporter(reports.append),
                self._maybe_observe_for_tyche() as observation,
                # Note that the data generation and test execution happen in the same
                # coverage context.  We may later split this, or tag each separately.
                collector,
            ):
                self.state._execute_once_for_engine(data)
        except StopTest:
            pass
        data.extra_information.reports = "\n".join(map(str, reports))  # type: ignore

        # In addition to coverage branches, use psudeo-coverage information provided via
        # the `hypothesis.event()` function - exploiting user-defined partitions
        # designed for diagnostic output to guide generation.  See
        # https://hypothesis.readthedocs.io/en/latest/details.html#hypothesis.event
        data.extra_information.behaviors = frozenset(  # type: ignore
            getattr(collector, "branches", ())  # might be a debug tracer instead
        ).union(
            f"event:{k}:{v}"
            for k, v in data.events.items()
            if not k.startswith(("invalid because", "Retried draw from "))
        )

        data.freeze()
        # Update the corpus and report any changes immediately for new coverage.  If no
        # new coverage, occasionally send an update anyway so we don't look stalled.
        self.status_counts[data.status] += 1
        # status_counts and elapsed_time have to be added to at the same time, without
        # saving a report between them, or we might violate monotonicity invariants.
        self.elapsed_time += time.perf_counter() - start
        assert observation.value is not None
        # don't save observations during replay. Observations are nondeterministic,
        # (via `run_start`, but also `timing`), and will end up duplicating corpus
        # observations here.
        if self.corpus.add(
            data.as_result(),
            observation=None if self.phase is Phase.REPLAY else observation.value,
        ):
            # TODO this is wrong for Status.INTERESTING examples (that are smaller
            # than the previous example for this interesting origin), which are
            # successfully added to the corpus but don't represent a new branch.
            self.since_new_branch = 0
        else:
            self.since_new_branch += 1
        if self.since_new_branch == 0 or self._should_save_timed_report():
            self._save_report(self._report)

        if self.elapsed_time > self.stop_shrinking_at:
            raise HitShrinkTimeoutError

        # The shrinker relies on returning the data object to be inspected.
        return data.as_result()

    def _should_save_timed_report(self) -> bool:
        # linear interpolation from 1 report/s at the start to 1 report/60s after
        # 5 minutes have passed
        increment = lerp(1, 60, min(self._last_saved_report_at / 60 * 5, 1))
        # A "timed report" is one that we expect to be discarded from the database
        # on the next saved report, but which serves as an incremental progress
        # marker for the dashboard.
        return self.elapsed_time > self._last_saved_report_at + increment

    @contextmanager
    def observe(self) -> Generator[Value[Optional[Observation]], None, None]:
        # we want to yield back to the caller without actually having gotten the
        # observation in the callback yet, but still be able to set its value from
        # inside the context manager. Yield a reference-forwarding Value instance.
        observation: Value[Optional[Observation]] = Value(None)

        def callback(h_observation: HypothesisObservation) -> None:
            if h_observation.type != "test_case":
                return

            # we should only get one observation per ConjectureData
            assert observation.value is None

            # run_start is relative to StateForActualGivenExecution, which we
            # re-use per FuzzProcess. Overwrite with the current timestamp for use
            # in sorting observations. This is not perfectly reliable in a
            # distributed setting, but is good enough.
            h_observation.run_start = time.time()
            # "arguments" duplicates part of the call repr in "representation".
            # We don't use this for anything, so drop it.
            h_observation.arguments = {}
            observation.value = Observation.from_hypothesis(h_observation)

        TESTCASE_CALLBACKS.append(callback)
        try:
            with (
                current_pytest_item.with_value(self.pytest_item)  # type: ignore
                if self.pytest_item is not None
                else nullcontext()
            ):
                yield observation
        finally:
            TESTCASE_CALLBACKS.remove(callback)

    @contextmanager
    def _maybe_observe_for_tyche(
        self,
    ) -> Generator[Value[Optional[Observation]], None, None]:
        # We're aiming for a rolling buffer of the last 300 observations, downsampling
        # to one per second if we're executing more than one test case per second.
        # Decide here, so that runtime doesn't bias our choice of what to observe.
        will_save = self.phase is Phase.GENERATE and (
            self.elapsed_time > self._last_observed + 1
        )
        with self.observe() as observation:
            try:
                yield observation
            finally:
                if will_save:
                    assert observation.value is not None
                    self.db.save_observation(
                        self.database_key, observation.value, discard_over=300
                    )
                    self._last_observed = self.elapsed_time

    def _save_report(self, report: Report) -> None:
        self.db.save_report(self.database_key, report)
        self._last_saved_report_at = self.elapsed_time

        # Having written the latest report, we can keep the database small
        # by dropping the previous report unless it differs from the latest in
        # an important way.
        if self._last_report and not (
            self._last_report.behaviors != report.behaviors
            or self._last_report.fingerprints != report.fingerprints
            or self._last_report.phase != report.phase
            or self.corpus.interesting_examples
            # always keep reports which discovered new coverage
            or self._last_report.since_new_branch == 0
        ):
            self.db.delete_report(self.database_key, self._last_report)

        self._last_report = report

    @property
    def _report(self) -> Report:
        assert sum(self.status_counts.values()) == self.ninputs
        assert self.phase is not None
        return Report(
            database_key=self.database_key_str,
            nodeid=self.nodeid,
            elapsed_time=self.elapsed_time,
            timestamp=time.time(),
            worker_uuid=self.worker_identity.uuid,
            status_counts=StatusCounts(self.status_counts),
            behaviors=len(self.corpus.behavior_counts),
            fingerprints=len(self.corpus.fingerprints),
            since_new_branch=(
                None
                if (self.ninputs == 0 or self.corpus.interesting_examples)
                else self.since_new_branch
            ),
            phase=self.phase,
        )

    @property
    def has_found_failure(self) -> bool:
        """If we've already found a failing example we might reprioritize."""
        return bool(self.corpus.interesting_examples)


def fuzz_several(targets: list[FuzzProcess], random_seed: Optional[int] = None) -> None:
    """Take N fuzz targets and run them all."""
    random = Random(random_seed)
    targets: SortedKeyList[FuzzProcess, int] = SortedKeyList(
        targets, lambda t: t.since_new_branch
    )

    # Loop forever: at each timestep, we choose a target using an epsilon-greedy
    # strategy for simplicity (TODO: improve this later) and run it once.
    # TODO: make this aware of test runtime, so it adapts for behaviors-per-second
    #       rather than behaviors-per-input.
    for target in targets:
        target.startup()

    dispatch: dict[bytes, list[FuzzProcess]] = defaultdict(list)
    for target in targets:
        dispatch[target.database_key].append(target)

    def on_event(listener_event: ListenerEventT) -> None:
        event = DatabaseEvent.from_event(listener_event)
        if event is None or event.database_key not in dispatch:
            return

        for target in dispatch[event.database_key]:
            target.on_event(event)

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


@lru_cache
def _git_head(*, in_directory: Optional[Path] = None) -> Optional[str]:
    if in_directory is not None:
        assert in_directory.is_dir()

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            timeout=10,
            text=True,
            cwd=in_directory,
            # stdout is captured by default; hide stderr too
            stderr=subprocess.PIPE,
        ).strip()
    except Exception:
        return None


@lru_cache
def worker_identity(*, in_directory: Optional[Path] = None) -> WorkerIdentity:
    """Returns a class identifying the machine running this code.

    This is intended to roughly represent the "unit of fuzz worker", so it includes
    the PID as well as hostname and (if in kubernetes) some pod identifiers.

    Tagging reports with this information makes it possible to tell when multiple
    runners have each contributed to a fuzzing campaign, more accurately count the
    total number of inputs, and so on.  In practice we don't care that much about
    precision here, because the code under test is likely to be changing too.
    """
    container_id = None
    with contextlib.suppress(Exception), open("/proc/self/cgroup") as f:
        for line in f:
            if "kubepods" in line:
                container_id = line.split("/")[-1].strip()

    python_version: Any = sys.version_info
    if python_version.releaselevel == "final":
        # drop releaselevel and serial for standard releases
        python_version = python_version[:3]

    return WorkerIdentity(
        uuid=process_uuid,
        operating_system=platform.system(),
        python_version=".".join(map(str, python_version)),
        hypothesis_version=hypothesis.__version__,
        hypofuzz_version=hypofuzz.__version__,
        pid=os.getpid(),
        hostname=socket.gethostname(),  # In K8s, this is typically the pod name
        pod_name=os.getenv("HOSTNAME"),
        pod_namespace=os.getenv("POD_NAMESPACE"),
        node_name=os.getenv("NODE_NAME"),
        pod_ip=os.getenv("POD_IP"),
        container_id=container_id,
        git_hash=_git_head(in_directory=in_directory),
    )
