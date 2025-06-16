import contextlib
import inspect
import math
import os
import platform
import socket
import subprocess
import sys
import time
from base64 import b64encode
from collections.abc import Generator, Set
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from enum import IntEnum
from functools import cache
from pathlib import Path
from random import Random
from typing import Any, ClassVar, Optional, TypeVar, Union, cast
from uuid import uuid4

import hypothesis
import hypothesis.internal.observability
from hypothesis import settings
from hypothesis.control import current_build_context
from hypothesis.database import BackgroundWriteDatabase
from hypothesis.internal.conjecture.choice import (
    ChoiceConstraintsT,
    ChoiceT,
    ChoiceTemplate,
    ChoiceTypeT,
    choice_permitted,
    choices_size,
)
from hypothesis.internal.conjecture.data import ConjectureData, Status
from hypothesis.internal.conjecture.providers import (
    COLLECTION_DEFAULT_MAX_SIZE,
    PrimitiveProvider,
)
from hypothesis.internal.escalation import current_pytest_item
from hypothesis.internal.intervalsets import IntervalSet
from hypothesis.internal.observability import InfoObservation, TestCaseObservation
from hypothesis.internal.reflection import (
    function_digest,
    get_pretty_function_description,
)
from sortedcontainers import SortedList

import hypofuzz
from hypofuzz.corpus import Behavior, Choices, Corpus
from hypofuzz.coverage import Branch, CoverageCollector
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
    test_keys_key,
)
from hypofuzz.mutator import BlackBoxMutator, CrossOverMutator
from hypofuzz.utils import lerp

T = TypeVar("T")
process_uuid = uuid4().hex

assert time.get_clock_info("perf_counter").monotonic, (
    "HypoFuzz relies on perf_counter being monotonic. This is guaranteed on "
    "CPython. Please open an issue if you hit this assertion."
)


def fresh_choice(
    choice_type: ChoiceTypeT, constraints: ChoiceConstraintsT, *, random: Random
) -> ChoiceT:
    cd = ConjectureData(random=random)
    choice = getattr(cd.provider, f"draw_{choice_type}")(**constraints)
    return cast(ChoiceT, choice)


# like choices_size, but handles ChoiceTemplate
def _choices_size(choices: tuple[Union[ChoiceT, ChoiceTemplate], ...]) -> int:
    return sum(
        1 if isinstance(choice, ChoiceTemplate) else choices_size([choice])
        for choice in choices
    )


def _should_save_timed_report(elapsed_time: float, last_saved_at: float) -> bool:
    # linear interpolation from 1 report/s at the start to 1 report/60s after
    # 5 minutes have passed
    increment = lerp(1, 60, min(last_saved_at / 60 * 5, 1))
    # A "timed report" is one that we expect to be discarded from the database
    # on the next saved report, but which serves as an incremental progress
    # marker for the dashboard.
    return elapsed_time > last_saved_at + increment


class ReplayPriority(IntEnum):
    FAILURE_SHRUNK = 0
    FAILURE_UNSHRUNK = 1
    COVERING = 2


@dataclass
class State:
    choices: ChoicesT
    replay_priority: Optional[ReplayPriority]
    start_time: float
    save_rolling_observation: bool
    branches: Optional[frozenset[Branch]] = None
    observation: Optional[Observation] = None
    extra_queue_data: Optional[Any] = None


# (priority, choice sequence, extra data)
ReplayQueueElement = tuple[ReplayPriority, ChoicesT, Optional[Any]]


class HypofuzzProvider(PrimitiveProvider):
    add_observability_callback: ClassVar[bool] = True

    def __init__(
        self,
        conjecturedata: Optional[ConjectureData],
        /,
        # allow test-time override of the coverage collector.
        collector: Optional[CoverageCollector] = None,
    ) -> None:
        super().__init__(conjecturedata)
        self.collector = collector
        self._index = 0
        self._replay_queue: SortedList[ReplayQueueElement] = SortedList(
            key=lambda x: (x[0], _choices_size(x[1]))
        )

        self.random = Random()
        self.elapsed_time = 0.0
        self.since_new_branch = 0
        self.phase: Optional[Phase] = None
        self.status_counts = StatusCounts()

        self._last_timed_report: Report | None = None
        self._last_saved_report_at = -math.inf
        self._last_observed = -math.inf
        self._started = False

        self.worker_identity: Optional[WorkerIdentity] = None
        self.database_key: Optional[bytes] = None
        self.corpus: Optional[Corpus] = None
        self.db: Optional[HypofuzzDatabase] = None
        # per-test-case state, reset at the beginning of each test case.
        self._state: Optional[State] = None

    @property
    def ninputs(self) -> int:
        return sum(self.status_counts.values())

    def _startup(self) -> None:
        if settings().database is None:
            raise ValueError("HypofuzzProvider must be used with a database")

        # TODO: make this a context manager we enter in per_test_case_context_manager,
        # so it resets after using hypofuzz?
        hypothesis.internal.observability.OBSERVABILITY_CHOICES = True
        hypothesis.internal.observability.OBSERVABILITY_COLLECT_COVERAGE = False

        self.db = HypofuzzDatabase(BackgroundWriteDatabase(settings().database))
        assert not self._started
        context = current_build_context()

        self.database_key = function_digest(context.wrapped_test.hypothesis.inner_test)  # type: ignore
        # TODO this means our nodeid might be different in the
        # @settings(backend="hypofuzz") case (which uses __func__.__name__)
        # and the hypofuzz worker case (which sets the current pytest item and
        # uses the nodeid). Is that ok? It means we can't rely on there being
        # one nodeid across all reports for a database_key. Probably fine, just
        # take the latest for display?
        self.nodeid = getattr(
            current_pytest_item.value, "nodeid", None
        ) or get_pretty_function_description(context.wrapped_test)

        self.worker_identity = worker_identity(
            in_directory=Path(inspect.getfile(context.wrapped_test)).parent
        )
        self.corpus = Corpus(self.db, self.database_key)

        # restore our saved minimal covering corpus, as well as any failures to
        # replay.
        for shrunk in [True, False]:
            priority = (
                ReplayPriority.FAILURE_SHRUNK
                if shrunk
                else ReplayPriority.FAILURE_UNSHRUNK
            )
            for choices in self.db.fetch_failures(self.database_key, shrunk=shrunk):
                observation = self.db.fetch_failure_observation(
                    self.database_key, choices
                )
                if observation is None:
                    continue
                self._enqueue(priority, choices, extra_data=observation)

        # TODO: do we need/want this?
        # self._enqueue(
        #     ReplayPriority.COVERING,
        #     (ChoiceTemplate(type="simplest", count=None),),
        # )
        for choices in self.db.fetch_corpus(self.database_key):
            self._enqueue(ReplayPriority.COVERING, choices)

        # Report that we've started this fuzz target
        self.db.save(test_keys_key, self.database_key)
        # save the worker identity once at startup
        self.db.save_worker_identity(self.database_key, self.worker_identity)

        if not self._replay_queue:
            # if no worker has ever worked on this test before, save an initial
            # Phase.GENERATE report, so the graph displays a point at (0, 0).
            #
            # This is a hack. We should move this to the dashboard plotting code
            # instead, by adding a virtual (0, 0) point.
            self.phase = Phase.GENERATE
            self._save_report(self._report)
            self.phase = None

        self._started = True

    def _enqueue(
        self,
        priority: ReplayPriority,
        choices: ChoicesT,
        *,
        extra_data: Optional[Any] = None,
    ) -> None:
        self._replay_queue.add((priority, choices, extra_data))

    def on_event(self, event: DatabaseEvent) -> None:
        # Some worker has found a new covering corpus element. Replay it in
        # this worker.
        if event.type == "save":
            if event.key is DatabaseEventKey.CORPUS:
                # the worker which saved this choice sequence might have been *us*,
                # or we might simply already have this choice sequence in our
                # corpus.
                if (
                    self.corpus is not None
                    and Choices(event.value) in self.corpus.corpus
                ):
                    return
                self._enqueue(ReplayPriority.COVERING, event.value)
            # (should we also replay failures found by other workers? we may not
            # want to stop early, since we could still find a different failure.
            # but I guess the same logic would apply to the worker which found the
            # failure..)

    def _start_phase(self, phase: Phase) -> None:
        if phase is self.phase:
            return
        if self.phase is not None:
            # don't save a report the very first time we start any phase
            self._save_report(self._report)
        self.phase = phase

    def _save_report(self, report: Report) -> None:
        assert self.database_key is not None
        assert self.corpus is not None
        assert self.db is not None

        self.db.save_report(self.database_key, report)
        self._last_saved_report_at = self.elapsed_time

        # A timed report is just a marker of the latest status of the test. It
        # contains no critical transition information.
        #
        # If a timed report is no longer the latest report (because we just saved
        # a new report), it's no longer useful, so delete it from the db.
        if self._last_timed_report:
            self.db.delete_report(self.database_key, self._last_timed_report)
            self._last_timed_report = None

    @property
    def _report(self) -> Report:
        assert self.phase is not None
        assert self.database_key is not None
        assert self.corpus is not None
        assert self.worker_identity is not None
        assert self.nodeid is not None

        return Report(
            database_key=b64encode(self.database_key).decode(),
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

    @contextmanager
    def per_test_case_context_manager(self) -> Generator[None, None, None]:
        # note that this only collects coverage during test execution, not
        # prep_args_kwargs_from_strategies. If we want to collect coverage during
        # input generation, we'll need a separate hypothesis-side hook.
        self.before_test_case()
        try:
            with self.collector or CoverageCollector() as collector:
                yield
        finally:
            assert self._state is not None
            self._state.branches = frozenset(collector.branches)
            # after_test_case is called by on_observation, since we want to wait
            # until we know a few things about how the execution went

    def before_test_case(self) -> None:
        if not self._started:
            self._startup()

        assert self.corpus is not None
        replay_priority = None
        extra_queue_data = None
        while self._replay_queue:
            (replay_priority, choices, extra_queue_data) = self._replay_queue.pop(0)

            # we checked if we had this choice sequence when we put it into the
            # replay_queue on on_event, but we check again here, since we might have
            # executed it in the interim.
            if (
                # Choices doesn't handle ChoiceTemplate
                all(not isinstance(choice, ChoiceTemplate) for choice in choices)
                and Choices(choices) in self.corpus.corpus
            ):
                continue

            self._start_phase(Phase.REPLAY)
            break
        else:
            # Eventually we'll want an MOpt-style adaptive weighting of all the
            # different mutators we could use.
            p_mutate = (
                0
                if self.ninputs == 0
                else (self.ninputs - len(self.corpus.corpus)) / self.ninputs
            )
            Mutator = (
                CrossOverMutator if self.random.random() < p_mutate else BlackBoxMutator
            )
            mutator = Mutator(self.corpus, self.random)

            choices = mutator.generate_choices()
            self._start_phase(Phase.GENERATE)

        # We're aiming for a rolling buffer of the last 300 observations, downsampling
        # to one per second if we're executing more than one test case per second.
        # Decide here, so that runtime doesn't bias our choice of what to observe.
        save_rolling_observation = self.elapsed_time > self._last_observed + 1
        start = time.perf_counter()

        self._state = State(
            choices=choices,
            replay_priority=replay_priority,
            start_time=start,
            extra_queue_data=extra_queue_data,
            save_rolling_observation=save_rolling_observation,
        )

    def on_observation(
        self, observation: Union[TestCaseObservation, InfoObservation]
    ) -> None:
        assert observation.type == "test_case"
        assert observation.property == self.nodeid
        self.after_test_case(observation)

    def after_test_case(self, observation: TestCaseObservation) -> None:
        assert self._state is not None
        assert self._state.branches is not None
        assert self.corpus is not None
        assert self.database_key is not None
        assert self.db is not None

        assert observation.type == "test_case"
        # run_start is normally relative to StateForActualGivenExecution, which we
        # re-use per FuzzTarget. Overwrite with the current timestamp for use
        # in sorting observations. This is not perfectly reliable in a
        # distributed setting, but is good enough.
        observation.run_start = self._state.start_time
        # "arguments" duplicates part of the call repr in "representation".
        # We don't use this for anything, and it can be substantial in size, so
        # drop it.
        observation.arguments = {}

        status = observation.metadata.data_status
        self.elapsed_time += time.perf_counter() - self._state.start_time
        self.status_counts[status] += 1

        if status is not Status.INTERESTING and self._state.replay_priority in [
            ReplayPriority.FAILURE_SHRUNK,
            ReplayPriority.FAILURE_UNSHRUNK,
        ]:
            # this failure didn't reproduce. It's either been fixed, is flaky,
            # or is specific to the worker's environment (e.g. only fails on
            # python 3.11, while this worker is on python 3.12).
            # In any case, remove it from the db.
            #
            # We know whether this failure was shrunk or not as of when we
            # took it out of the db (via replay_priority). But I'm not confident that
            # it's not possible for another worker to move the same choice
            # sequence from unshrunk to shrunk - and failures are rare +
            # deletions cheap. Just try deleting from both.
            failure_observation = self._state.extra_queue_data
            assert failure_observation is not None
            assert isinstance(failure_observation, Observation)
            # failures are hard to find, and shrunk ones even more so. If a failure
            # does not reproduce, only delete it if it's been more than 8 days,
            # so we don't accidentally delete a useful failure.
            if (
                date.fromtimestamp(failure_observation.run_start) + timedelta(days=8)
                < date.today()
            ):
                for shrunk in [True, False]:
                    self.db.delete_failure(
                        self.database_key,
                        self._state.choices,
                        failure_observation,
                        shrunk=shrunk,
                    )

        # TODO this is a real type error, we need to unify the Branch namedtuple
        # with the real usages of `behaviors` here
        behaviors: Set[Behavior] = self._state.branches | (  # type: ignore
            # include |event| and |target| as pseudo-branch behaviors.
            # TODO this treats every distinct value of target and every event
            # payload as a distinct behavior. We probably want to bucket `v` for
            # target (but not event?)
            {
                # v is "" for e.g. an `event` call without a payload argument
                f"event:{k if v == '' else f'{k}:{v}'}"
                for k, v in observation.features.items()
                if not k.startswith(("invalid because", "Retried draw from "))
            }
        )

        branches_before = len(self.corpus.behavior_counts)
        self.corpus.add(
            observation,
            behaviors=behaviors,
            # don't save observations during replay. Observations are nondeterministic,
            # (via `run_start`, but also `timing`), and will end up duplicating corpus
            # observations here.
            save_observation=self.phase is not Phase.REPLAY,
        )

        if branches_before != len(self.corpus.behavior_counts):
            self.since_new_branch = 0
        else:
            self.since_new_branch += 1

        if self.since_new_branch == 0:
            self._save_report(self._report)
        elif _should_save_timed_report(self.elapsed_time, self._last_saved_report_at):
            report = self._report
            self._save_report(report)
            self._last_timed_report = report

        if self.phase is Phase.GENERATE and self._state.save_rolling_observation:
            self.db.save_observation(
                self.database_key,
                Observation.from_hypothesis(observation),
                discard_over=300,
            )
            self._last_observed = self.elapsed_time

        self._state = None

    def _fresh_choice(
        self, choice_type: ChoiceTypeT, constraints: ChoiceConstraintsT
    ) -> ChoiceT:
        return fresh_choice(choice_type, constraints, random=self.random)

    def _pop_choice(
        self, choice_type: ChoiceTypeT, constraints: ChoiceConstraintsT
    ) -> ChoiceT:
        assert self._state is not None
        if self._index >= len(self._state.choices):
            # past our prefix. draw a random choice
            return self._fresh_choice(choice_type, constraints)

        choice = self._state.choices[self._index]
        popped_choice_type = {
            int: "integer",
            float: "float",
            bool: "boolean",
            bytes: "bytes",
            str: "string",
        }[type(choice)]
        if choice_type != popped_choice_type or not choice_permitted(
            choice, constraints
        ):
            # misalignment. draw a random choice
            choice = self._fresh_choice(choice_type, constraints)

        self._index += 1
        return choice

    def draw_boolean(
        self,
        p: float = 0.5,
    ) -> bool:
        choice = self._pop_choice("boolean", {"p": p})
        assert isinstance(choice, bool)
        return choice

    def draw_integer(
        self,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
        *,
        # weights are for choosing an element index from a bounded range
        weights: Optional[dict[int, float]] = None,
        shrink_towards: int = 0,
    ) -> int:
        choice = self._pop_choice(
            "integer",
            {
                "min_value": min_value,
                "max_value": max_value,
                "weights": weights,
                "shrink_towards": shrink_towards,
            },
        )
        assert isinstance(choice, int)
        return choice

    def draw_float(
        self,
        *,
        min_value: float = -math.inf,
        max_value: float = math.inf,
        allow_nan: bool = True,
        smallest_nonzero_magnitude: float,
    ) -> float:
        choice = self._pop_choice(
            "float",
            {
                "min_value": min_value,
                "max_value": max_value,
                "allow_nan": allow_nan,
                "smallest_nonzero_magnitude": smallest_nonzero_magnitude,
            },
        )
        assert isinstance(choice, float)
        return choice

    def draw_string(
        self,
        intervals: IntervalSet,
        *,
        min_size: int = 0,
        max_size: int = COLLECTION_DEFAULT_MAX_SIZE,
    ) -> str:
        choice = self._pop_choice(
            "string",
            {"intervals": intervals, "min_size": min_size, "max_size": max_size},
        )
        assert isinstance(choice, str)
        return choice

    def draw_bytes(
        self,
        min_size: int = 0,
        max_size: int = COLLECTION_DEFAULT_MAX_SIZE,
    ) -> bytes:
        choice = self._pop_choice("bytes", {"min_size": min_size, "max_size": max_size})
        assert isinstance(choice, bytes)
        return choice


@cache
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


@cache
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
