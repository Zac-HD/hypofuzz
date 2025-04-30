"""Adaptive fuzzing for property-based tests using Hypothesis."""

import contextlib
import inspect
import itertools
import os
import platform
import socket
import subprocess
import sys
import threading
import time
from base64 import b64encode
from collections.abc import Callable, Generator
from functools import lru_cache
from pathlib import Path
from random import Random
from typing import Any, Generic, Optional, TypeVar, Union
from uuid import uuid4

import hypothesis
from hypothesis import HealthCheck, settings
from hypothesis.core import (
    StateForActualGivenExecution,
    Stuff,
    process_arguments_to_given,
)
from hypothesis.database import ExampleDatabase
from hypothesis.errors import StopTest
from hypothesis.internal.conjecture.choice import ChoiceT, ChoiceTemplate
from hypothesis.internal.conjecture.data import (
    ConjectureData,
    ConjectureResult,
    Status,
    _Overrun,
)
from hypothesis.internal.conjecture.engine import RunIsComplete
from hypothesis.internal.observability import TESTCASE_CALLBACKS
from hypothesis.internal.reflection import function_digest, get_signature
from hypothesis.reporting import with_reporter
from sortedcontainers import SortedKeyList

import hypofuzz
from hypofuzz.corpus import (
    BlackBoxMutator,
    CrossOverMutator,
    Pool,
    get_shrinker,
)
from hypofuzz.coverage import CoverageCollectionContext
from hypofuzz.database import (
    Metadata,
    Phase,
    Report,
    StatusCounts,
    WorkerIdentity,
    get_db,
)
from hypofuzz.provider import HypofuzzProvider

T = TypeVar("T")

process_uuid = uuid4().hex


# hypothesis.utils.dynamicvaraible, but without the with_value context manager.
# Essentially just a reference to a value.
class Value(Generic[T]):
    def __init__(self, default: T) -> None:
        self.default = default
        self.data = threading.local()

    @property
    def value(self) -> T:
        return getattr(self.data, "value", self.default)

    @value.setter
    def value(self, value: T) -> None:
        self.data.value = value


class HitShrinkTimeoutError(Exception):
    pass


class HypofuzzStateForActualGivenExecution(StateForActualGivenExecution):
    def _should_trace(self) -> bool:
        # we're handling our own coverage collection, both for observability and
        # for failing examples (explain phase).
        return False


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
        nodeid: Optional[str] = None,
        extra_kw: Optional[dict[str, object]] = None,
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
            nodeid=nodeid,
            database_key=function_digest(wrapped_test.hypothesis.inner_test),
            hypothesis_database=getattr(
                wrapped_test, "_hypothesis_internal_use_settings", settings.default
            ).database
            or settings.default.database,
            wrapped_test=wrapped_test,
        )

    def __init__(
        self,
        test_fn: Callable,
        stuff: Stuff,
        *,
        random_seed: int = 0,
        nodeid: Optional[str] = None,
        database_key: bytes,
        hypothesis_database: ExampleDatabase,
        wrapped_test: Callable,
    ) -> None:
        """Construct a FuzzProcess from specific arguments."""
        # The actual fuzzer implementation
        self.random = Random(random_seed)
        self._test_fn = test_fn
        self._stuff = stuff
        self.nodeid = nodeid or test_fn.__qualname__
        self.database_key = database_key

        self.state = HypofuzzStateForActualGivenExecution(  # type: ignore
            stuff,
            self._test_fn,
            settings(
                database=None, deadline=None, suppress_health_check=list(HealthCheck)
            ),
            self.random,
            wrapped_test,
        )

        # The seed pool is responsible for managing all seed state, including saving
        # novel seeds to the database.  This includes tracking how often each branch
        # has been hit, minimal covering examples, and so on.
        self.pool = Pool(hypothesis_database, database_key)
        self._mutator_blackbox = BlackBoxMutator(self.pool, self.random)
        self._mutator_crossover = CrossOverMutator(self.pool, self.random)

        # Set up the basic data that we'll track while fuzzing
        self.ninputs = 0
        self.elapsed_time = 0.0
        self.stop_shrinking_at = float("inf")
        self.since_new_cov = 0
        self.status_counts = dict.fromkeys(Status, 0)
        self.phase: Optional[Phase] = None
        # Any new examples from the database will be added to this replay queue
        self._replay_queue: list[tuple[Union[ChoiceT, ChoiceTemplate], ...]] = []
        # After replay, we stay in blackbox mode for a while, until we've generated
        # 1000 consecutive examples without new coverage, and then switch to mutation.
        self._early_blackbox_mode = True
        self._last_report: Report | None = None

        # Track observability data
        self._observations_key = database_key + b".observations"
        self._last_observed = 0.0

    def startup(self) -> None:
        """Set up initial state and prepare to replay the saved behaviour."""
        # Report that we've started this fuzz target
        get_db().save(b"hypofuzz-test-keys", self.database_key)
        # Next, restore progress made in previous runs by loading our saved examples.
        # This is meant to be the minimal set of inputs that exhibits all distinct
        # behaviours we've observed to date.  Replaying takes longer than restoring
        # our data structures directly, but copes much better with changed behaviour.
        self._replay_queue.extend(self.pool.fetch())
        self._replay_queue.append((ChoiceTemplate(type="simplest", count=None),))

    def _start_phase(self, phase: Phase) -> None:
        if phase is self.phase:
            return
        if self.phase is not None:
            # don't save a report the very first time we start a phase
            self._save_report(self._report)
            self._replace_metadata(self._metadata)
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
        if self._replay_queue:
            self._start_phase(Phase.REPLAY)
            choices = self._replay_queue.pop()
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
        # If we've been stable for a little while, try loading new examples from the
        # database.  We do this unconditionally because even if this fuzzer doesn't
        # know of other concurrent runs, there may be e.g. a test process sharing the
        # database.  We do make it infrequent to manage the overhead though.
        if self.ninputs % 1000 == 0 and self.since_new_cov > 1000:
            self._replay_queue.extend(self.pool.fetch())

        # seen_count = len(self.pool.arc_counts)
        # Run the input
        result = self._run_test_on(self.generate_data())

        if result.status is Status.INTERESTING:
            assert not isinstance(result, _Overrun)
            # Shrink to our minimal failing example, since we'll stop after this.
            self._start_phase(Phase.SHRINK)
            shrinker = get_shrinker(
                self.pool,
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
            self._save_report(self._report)
            self._replace_metadata(self._metadata)

        # Consider switching out of blackbox mode.
        if self.since_new_cov >= 1000 and not self._replay_queue:
            self._early_blackbox_mode = False

        # NOTE: this distillation logic works fine, it's just discovering new coverage
        # much more slowly than jumping directly to mutational mode.
        # if len(self.pool.arc_counts) > seen_count and not self._early_blackbox_mode:
        #     self._start_phase(Phase.DISTILL)
        #     self.pool.distill(self._run_test_on, self.random)

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
        collector = collector or CoverageCollectionContext()
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
        # pass current string_repr through to ConjectureResult.
        # Note that observability has to be enabled (i.e. something has to be
        # in TESTCASE_CALLBACKS) for hypothesis to fill _string_repr.
        data.extra_information.string_repr = self.state._string_repr  # type: ignore
        data.extra_information.reports = "\n".join(map(str, reports))  # type: ignore

        # In addition to coverage branches, use psudeo-coverage information provided via
        # the `hypothesis.event()` function - exploiting user-defined partitions
        # designed for diagnostic output to guide generation.  See
        # https://hypothesis.readthedocs.io/en/latest/details.html#hypothesis.event
        data.extra_information.branches = frozenset(  # type: ignore
            getattr(collector, "branches", ())  # might be a debug tracer instead
        ).union(
            f"event:{k}:{v}"
            for k, v in data.events.items()
            if not k.startswith(("invalid because", "Retried draw from "))
        )

        data.freeze()
        # Update the pool and report any changes immediately for new coverage.  If no
        # new coverage, occasionally send an update anyway so we don't look stalled.
        self.status_counts[data.status] += 1
        assert observation.value is not None
        if self.pool.add(data.as_result(), observation=observation.value):
            self.since_new_cov = 0
        else:
            self.since_new_cov += 1
        if 0 in (self.since_new_cov, self.ninputs % 100):
            self._save_report(self._report)
            self._replace_metadata(self._metadata)

        self.elapsed_time += time.perf_counter() - start
        if self.elapsed_time > self.stop_shrinking_at:
            raise HitShrinkTimeoutError

        # The shrinker relies on returning the data object to be inspected.
        return data.as_result()

    @contextlib.contextmanager
    def _maybe_observe_for_tyche(self) -> Generator[Value[Optional[dict]], None, None]:
        # We're aiming for a rolling buffer of the last 300 observations, downsampling
        # to one per second if we're executing more than one test case per second.
        # Decide here, so that runtime doesn't bias our choice of what to observe.
        will_save = self.phase is Phase.GENERATE and (
            self.elapsed_time > self._last_observed + 1
        )
        # we want to refer to and set this value inside and outside of the context
        # manager. Use a wrapping Value class as a reference-forwarder.
        observation: Value[Optional[dict]] = Value(None)

        def callback(test_case: dict) -> None:
            if test_case["type"] != "test_case":
                return
            assert observation.value is None
            observation.value = test_case

        TESTCASE_CALLBACKS.append(callback)
        try:
            yield observation
        finally:
            TESTCASE_CALLBACKS.pop()
        if will_save:
            assert observation.value is not None
            get_db().save_observation(
                self._observations_key, observation.value, discard_over=300
            )

    def _save_report(self, report: Report) -> None:
        db = get_db()
        db.save_report(self.database_key, report)

        # Having written the latest report, we can avoid bloating the database
        # by dropping the previous report if it differs from the latest in more
        # than just runtime.
        if self._last_report and not (
            self._last_report.branches != report.branches
            or self._last_report.phase != report.phase
            or self.pool.interesting_examples
            # always keep reports which discovered new coverage
            or self._last_report.since_new_cov == 0
        ):
            db.delete_report(self.database_key, self._last_report)

        self._last_report = report

    def _replace_metadata(self, metadata: Metadata) -> None:
        db = get_db()
        db.replace_metadata(self.database_key, metadata)

    @property
    def _report(self) -> Report:
        """Summarise current state to send to dashboard."""
        assert sum(self.status_counts.values()) == self.ninputs
        assert self.phase is not None
        return Report(
            database_key=b64encode(self.database_key).decode(),
            nodeid=self.nodeid,
            elapsed_time=self.elapsed_time,
            timestamp=time.time(),
            worker=worker_identity(
                in_directory=Path(inspect.getfile(self._test_fn)).parent
            ),
            status_counts=StatusCounts(self.status_counts),
            branches=len(self.pool.arc_counts),
            since_new_cov=(
                None
                if (self.ninputs == 0 or self.pool.interesting_examples)
                else self.since_new_cov
            ),
            phase=self.phase,
        )

    @property
    def _metadata(self) -> Metadata:
        return Metadata(
            nodeid=self.nodeid,
            seed_pool=self.pool.json_report,
            failures=[ls for _, ls in self.pool.interesting_examples.values()],
        )

    @property
    def has_found_failure(self) -> bool:
        """If we've already found a failing example we might reprioritize."""
        return bool(self.pool.interesting_examples)


def fuzz_several(*targets_: FuzzProcess, random_seed: Optional[int] = None) -> None:
    """Take N fuzz targets and run them all."""
    # TODO: this isn't actually multi-process yet, and that's bad.
    rand = Random(random_seed)
    targets = SortedKeyList(targets_, lambda t: t.since_new_cov)

    # Loop forever: at each timestep, we choose a target using an epsilon-greedy
    # strategy for simplicity (TODO: improve this later) and run it once.
    # TODO: make this aware of test runtime, so it adapts for branches-per-second
    #       rather than branches-per-input.
    for t in targets:
        t.startup()
    for i in itertools.count():
        if i % 20 == 0:
            t = targets.pop(rand.randrange(len(targets)))
            t.run_one()
            targets.add(t)
        else:
            targets[0].run_one()
            if len(targets) > 1 and targets.key(targets[0]) > targets.key(targets[1]):
                # pay our log-n cost to keep the list sorted
                targets.add(targets.pop(0))
            elif targets[0].has_found_failure:
                print(f"found failing example for {targets[0].nodeid}")
                targets.pop(0)
            if not targets:
                return
    raise NotImplementedError("unreachable")


@lru_cache
def _git_head(*, in_directory: Optional[Path] = None) -> Optional[str]:
    if in_directory is not None:
        assert in_directory.is_dir()

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], timeout=10, text=True, cwd=in_directory
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
