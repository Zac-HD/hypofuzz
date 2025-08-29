import math
import time
from base64 import b64encode
from collections.abc import Generator, Set
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from enum import IntEnum
from random import Random
from typing import Any, ClassVar, Optional, TypeVar, Union, cast

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

from hypofuzz.corpus import Behavior, Choices, Corpus
from hypofuzz.coverage import Branch, CoverageCollector
from hypofuzz.database import (
    ChoicesT,
    DatabaseEvent,
    DatabaseEventKey,
    FailureState,
    HypofuzzDatabase,
    Observation,
    Phase,
    Report,
    Stability,
    StatusCounts,
    test_keys_key,
)
from hypofuzz.detection import in_hypofuzz_run
from hypofuzz.mutator import BlackBoxMutator, CrossOverMutator
from hypofuzz.utils import lerp, process_uuid

T = TypeVar("T")

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


class QueuePriority(IntEnum):
    FAILURE_SHRUNK = 0
    FAILURE_UNSHRUNK = 1
    FAILURE_FIXED = 2
    # we actually want STABILITY to have higher priority than COVERING, so that
    # corpus inputs which find new covered are re-executed immediately, without
    # waiting for a scan of replaying the full corpus once and enqueuing all their
    # stability re-executions.
    #
    # Failures still take priority over stability re-executions, however.
    STABILITY = 3
    # COVERING_REPLAY is a corpus element from the initial database load. COVERING
    # is a corpus element from another worker.
    COVERING_REPLAY = 4
    COVERING = 5


@dataclass
class State:
    choices: ChoicesT
    priority: Optional[QueuePriority]
    start_time: float
    save_rolling_observation: bool
    # whether to re-execute this observation for stability, or save it with
    # stability=None
    rolling_observation_stability: bool

    choice_index: int = 0
    branches: Optional[frozenset[Branch]] = None
    observation: Optional[Observation] = None
    extra_queue_data: Optional[Any] = None


# (priority, choice sequence, extra_data)
QueueElement = tuple[QueuePriority, ChoicesT, Optional[Any]]


def bucket_target_value(v: Any) -> Any:
    # technically, someone could do event("target", not_an_int) and get us
    # confused with a target() call. We could/should track this provenance more
    # carefully in observation.features
    if not isinstance(v, (int, float)):
        return v

    # bucket by (base 2) orders of magnitude.
    sign = math.copysign(1, v)
    bucketed = 0 if v == 0 else math.log2(abs(v))
    return sign * (int(bucketed) if math.isfinite(bucketed) else math.inf)


def bucket_features(features: dict[str, Any]) -> set[str]:
    bucketed = set()
    for k, v in features.items():
        if k.startswith(("invalid because", "Retried draw from ")):
            continue
        if k == "target":
            v = bucket_target_value(v)
        bucketed.add(f"event:{k if v == '' else f'{k}:{v}'}")
    return bucketed


class HypofuzzProvider(PrimitiveProvider):
    add_observability_callback: ClassVar[bool] = True

    # the time between rolling observations, in seconds
    ROLLING_OBSERVATION_INTERVAL: float = 1.0
    # A limit on the percentage of time which we spend in re-executing rolling
    # observations for stability, relative to self.elapsed_time. A value of 0.01
    # indicates that we should spend no more than 1% of elapsed time on observation
    # stability re-execution
    OBSERVATION_REEXECUTION_LIMIT: float = 0.02

    def __init__(
        self,
        conjecturedata: Optional[ConjectureData],
        /,
        # allow test-time override of the coverage collector.
        collector: Optional[CoverageCollector] = None,
        database_key: Optional[bytes] = None,
    ) -> None:
        super().__init__(conjecturedata)
        self.collector = collector

        # These two attributes are incremented for every input executed,
        # regardless of origin. This tracks the *total* effort expended by this
        # worker on this test.
        #
        # These attributes are written to reports and used for coverage graph
        # display. They are NOT used for estimator state.
        self.status_counts = StatusCounts()
        self.elapsed_time: float = 0.0
        # These four attributes are incremented only for inputs generated from a
        # mutator. This tracks the *useful* effort expended by this worker on this
        # test.
        #
        # These four attributes are not written to reports. They are used for
        # estimator state.
        #
        # Invariant: elapsed_time_mutated <= elapsed_time and
        # status_counts_mutated <= status_counts.
        self.status_counts_mutated = StatusCounts()
        self.elapsed_time_mutated: float = 0.0
        self.since_new_behavior: int = 0
        self.since_new_fingerprint: int = 0

        self.random = Random()
        self.phase: Optional[Phase] = None
        # there's a subtle bug here: we don't want to defer computation of
        # database_key until _startup, because by then the _hypothesis_internal_add_digest
        # added to the shared inner_test function may have been changed to a
        # parametrization that isn't us. This is only a problem in Hypofuzz since
        # there's no concurrency like this in Hypothesis (yet?).
        #
        # Passing the database key upfront avoids from FuzzTarget avoids this. If
        # it's not passed, we're being used from Hypothesis, and it's fine to defer
        # computation.
        self.database_key: Optional[bytes] = database_key
        self.corpus: Optional[Corpus] = None
        self.db: Optional[HypofuzzDatabase] = None

        self._choices_queue: SortedList[QueueElement] = SortedList(
            key=lambda x: (x[0], _choices_size(x[1]))
        )
        # we tracked the choice sequences that we initially loaded from the
        # database for replay, because we don't want to save observations for
        # these, even if they add new coverage (which they probably will, since
        # they were saved as corpus/failures).
        self._loaded_for_replay: set[Choices] = set()

        self._last_timed_report: Report | None = None
        self._last_saved_report_at = -math.inf
        self._last_observed = -math.inf
        # per-test-case state, reset at the beginning of each test case.
        self._state: Optional[State] = None
        self._started = False
        # we use this to ignore the on_observation observation if we error in
        # startup
        self._errored_in_startup = False
        self.most_recent_observation: TestCaseObservation | None = None
        # used to limit the time spent in re-executing observations for stability.
        self._time_in_observation_stability: float = 0.0

    @property
    def ninputs(self) -> int:
        return sum(self.status_counts.values())

    def _startup(self) -> None:
        db = settings().database
        if db is None:
            self._errored_in_startup = True
            raise ValueError(
                '@settings(backend="hypofuzz") cannot be combined with '
                "@settings(database=None), because fuzzing is substantially less "
                "powerful without the ability to persist choice sequences which "
                "discover new behaviors. "
                "\n\n"
                "If you cannot use a persistent database in this test, you can "
                "also pass @settings(database=InMemoryExampleDatabase()), which "
                "will silence this error (but not persist discovered behaviors "
                "across runs)."
            )
        if in_hypofuzz_run():
            # we wouldn't have collected this test otherwise
            assert db is not None
            db = BackgroundWriteDatabase(db)

        self.db = HypofuzzDatabase(db)

        # TODO: make this a context manager we enter in per_test_case_context_manager,
        # so it resets after using hypofuzz?
        hypothesis.internal.observability.OBSERVABILITY_CHOICES = True
        hypothesis.internal.observability.OBSERVABILITY_COLLECT_COVERAGE = False

        assert not self._started
        wrapped_test = current_build_context().wrapped_test

        if self.database_key is None:
            self.database_key = function_digest(wrapped_test.hypothesis.inner_test)  # type: ignore

        # TODO this means our nodeid might be different in the
        # @settings(backend="hypofuzz") case (which uses __func__.__name__)
        # and the hypofuzz worker case (which sets the current pytest item and
        # uses the nodeid). Is that ok? It means we can't rely on there being
        # one nodeid across all reports for a database_key. Probably fine, just
        # take the latest for display?
        self.nodeid = getattr(
            current_pytest_item.value, "nodeid", None
        ) or get_pretty_function_description(wrapped_test)

        self.corpus = Corpus(self.db, self.database_key)

        # restore our saved minimal covering corpus, as well as any failures to
        # replay.
        for state in [FailureState.SHRUNK, FailureState.UNSHRUNK, FailureState.FIXED]:
            priority = {
                FailureState.SHRUNK: QueuePriority.FAILURE_SHRUNK,
                FailureState.UNSHRUNK: QueuePriority.FAILURE_UNSHRUNK,
                FailureState.FIXED: QueuePriority.FAILURE_FIXED,
            }[state]
            for choices in self.db.failures(state=state).fetch(self.database_key):
                observation = self.db.failure_observations(state=state).fetch(
                    self.database_key, choices
                )
                if observation is None:
                    continue
                self._enqueue(priority, choices, extra_data=observation)
                self._loaded_for_replay.add(Choices(choices))

        # TODO: do we need/want this?
        # self._enqueue(
        #     ReplayPriority.COVERING,
        #     (ChoiceTemplate(type="simplest", count=None),),
        # )
        for choices in self.db.corpus.fetch(self.database_key):
            self._enqueue(QueuePriority.COVERING_REPLAY, choices)
            self._loaded_for_replay.add(Choices(choices))

        # Report that we've started this fuzz target
        self.db.save(test_keys_key, self.database_key)
        # clear out any fatal failures now that we've successfully started this
        # test
        self.db.fatal_failures.delete(self.database_key)

        if not self._loaded_for_replay:
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
        priority: QueuePriority,
        choices: ChoicesT,
        *,
        extra_data: Optional[Any] = None,
    ) -> None:
        self._choices_queue.add((priority, choices, extra_data))

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
                self._enqueue(QueuePriority.COVERING, event.value)
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

        self.db.reports.save(self.database_key, report)
        self._last_saved_report_at = self.elapsed_time

        # A timed report is just a marker of the latest status of the test. It
        # contains no critical transition information.
        #
        # If a timed report is no longer the latest report (because we just saved
        # a new report), it's no longer useful, so delete it from the db.
        if self._last_timed_report:
            self.db.reports.delete(self.database_key, self._last_timed_report)
            self._last_timed_report = None

    @property
    def _report(self) -> Report:
        assert self.phase is not None
        assert self.database_key is not None
        assert self.corpus is not None
        assert self.nodeid is not None

        return Report(
            database_key=b64encode(self.database_key).decode(),
            nodeid=self.nodeid,
            elapsed_time=self.elapsed_time,
            timestamp=time.time(),
            worker_uuid=process_uuid,
            status_counts=StatusCounts(self.status_counts),
            behaviors=len(self.corpus.behavior_counts),
            fingerprints=len(self.corpus.fingerprints),
            since_new_behavior=(
                None
                if (self.ninputs == 0 or self.corpus.interesting_examples)
                else self.since_new_behavior
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

    def _test_case_choices(
        self,
    ) -> tuple[ChoicesT, Optional[QueuePriority], Optional[Any]]:
        # return the choices for this test case. The choices might come from
        # either _choices_queue, or a mutator.

        assert self.corpus is not None
        while self._choices_queue:
            (priority, choices, extra_queue_data) = self._choices_queue.pop(0)

            # we checked if we had this choice sequence when we put it into the
            # replay_queue on on_event, but we check again here, since we might have
            # executed it in the interim.
            if (
                # Choices doesn't handle ChoiceTemplate
                all(not isinstance(choice, ChoiceTemplate) for choice in choices)
                and Choices(choices) in self.corpus.corpus
            ):
                continue

            self._start_phase(
                Phase.REPLAY
                if priority is QueuePriority.COVERING_REPLAY
                # don't switch out of Phase.REPLAY during stability re-executions
                # TODO also consider not switching out of replay when executing
                # queued failures?
                or (priority is QueuePriority.STABILITY and self.phase is Phase.REPLAY)
                else Phase.GENERATE
            )
            return (choices, priority, extra_queue_data)

        # if both the replay and choices queues were empty, we generate a new
        # choice sequence via mutation.

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
        return (choices, None, None)

    def _should_save_rolling_observation(
        self, *, priority: Optional[QueuePriority]
    ) -> bool:
        return (
            self.phase is Phase.GENERATE
            and self.elapsed_time
            > self._last_observed + self.ROLLING_OBSERVATION_INTERVAL
            # We only save rolling observations if the queue priorty is None, ie the
            # input was generated via mutation. This prevents biasing towards replayed
            # choice sequences.
            and priority is None
        )

    def before_test_case(self) -> None:
        if not self._started:
            self._startup()

        (choices, priority, extra_queue_data) = self._test_case_choices()
        # We're aiming for a rolling buffer of the last n observations, downsampling
        # to one per second if we're executing more than one test case per second.
        # Decide whether to save the observation before running, so that runtime
        # doesn't bias our choice of what to observe.
        save_rolling_observation = self._should_save_rolling_observation(
            priority=priority
        )
        # Limit observations to a percentage of total runtime. If a test only
        # gets 1 exec/s, we could otherwise spend 50% of our time in replay.
        rolling_observation_stability = (
            self._time_in_observation_stability
            <= (self.elapsed_time * self.OBSERVATION_REEXECUTION_LIMIT)
            # Sanity check: dont limit under very low runtimes.
            # This is mostly for tests which monkeypatch should_save and have
            # 0 runtime overhead. But it's good in general to not make too many
            # runtime decisions until we have a reasonable sample size.
            or self.elapsed_time < 1
        )
        start = time.perf_counter()

        self._state = State(
            choices=choices,
            priority=priority,
            start_time=start,
            extra_queue_data=extra_queue_data,
            save_rolling_observation=save_rolling_observation,
            rolling_observation_stability=rolling_observation_stability,
        )

    def on_observation(
        self, observation: Union[TestCaseObservation, InfoObservation]
    ) -> None:
        assert observation.type == "test_case"
        if self._errored_in_startup:
            # this is the observation for the exception we raised in _startup,
            # we don't want to do anything here (or trigger internal assertions
            # from not finishing startup)
            assert observation.status == "failed"
            return

        assert observation.property == self.nodeid
        # HypofuzzProvider doesn't use this anywhere, but we save it so FuzzWorker
        # can access it when saving failures corresponding to test framework skips.
        self.most_recent_observation = observation
        self.after_test_case(observation)

    def downgrade_failure(
        self, choices: ChoicesT, observation: Observation, *, state: FailureState
    ) -> None:
        """
        Called when this worker did not reproduce a failure. We move SHRUNK
        and UNSHRUNK failures to FIXED, and delete FIXED failures if it's been
        more than 8 days.
        """
        assert self.db is not None
        assert self.database_key is not None

        # this failure didn't reproduce. It's either been fixed, is flaky,
        # or is specific to the worker's environment (e.g. only fails on
        # python 3.11, while this worker is on python 3.12).
        # In any case, remove it from the db.

        if state in [FailureState.SHRUNK, FailureState.UNSHRUNK]:
            # We know whether this failure was shrunk or not as of when we
            # took it out of the db (via its priority). But I'm not confident that
            # it's not possible for another worker to move the same choice
            # sequence from unshrunk to shrunk - and failures are rare +
            # deletions cheap. Just try deleting from both.
            for failure_state in [FailureState.SHRUNK, FailureState.UNSHRUNK]:
                self.db.failures(state=failure_state).delete(
                    self.database_key,
                    choices,
                )

            # move it to the FIXED key so we still try it in the future
            self.db.failures(state=FailureState.FIXED).save(
                self.database_key, choices, observation
            )

        if (
            state is FailureState.FIXED
            and date.fromtimestamp(observation.run_start) + timedelta(days=8)
            < date.today()
        ):
            # failures are hard to find, and shrunk ones even more so. If a failure
            # does not reproduce, only delete it if it's been more than 8 days,
            # so we don't accidentally delete a useful failure.
            self.db.failures(state=FailureState.SHRUNK).delete(
                self.database_key,
                choices,
            )

    def _save_observation(
        self, observation: TestCaseObservation, *, stability: Optional[Stability]
    ) -> None:
        assert self.db is not None
        assert self.database_key is not None
        self.db.rolling_observations.save(
            self.database_key,
            Observation.from_hypothesis(observation, stability=stability),
            discard_over=300,
        )
        self._last_observed = self.elapsed_time

    def after_test_case(self, observation: TestCaseObservation) -> None:
        if self._state is None:
            # This is possible when the user interrupts the program with ctrl+c,
            # ie raises KeyboardInterrupt.
            # * after_test_case finishes (setting self._state = None).
            # * Hypothesis starts a new test case. It is inside of execute_once,
            #   but hasn't yet called per_test_case_context_manager, which is what
            #   calls before_test_case.
            # * KeyboardInterrupt is raised. Because we're inside the
            #   _execute_once_for_engine try/except, an observation gets delivered.
            #   But because we haven't yet entered per_test_case_context_manager,
            #   self._state is still None.
            #
            # I don't think a principled hypothesis-side fix for this is possible,
            # except maybe specially handling KeyboardInterrupt + observability.
            #
            # For the moment, we'll ignore this case in hypofuzz.
            return

        assert self._state is not None
        assert self._state.branches is not None
        assert self.corpus is not None
        assert self.database_key is not None
        assert self.db is not None
        assert observation.type == "test_case"
        # because we set OBSERVABILITY_CHOICES in _startup
        assert observation.metadata.choice_nodes is not None

        elapsed_time = time.perf_counter() - self._state.start_time
        # run_start is normally relative to StateForActualGivenExecution, which we
        # re-use per FuzzTarget. Overwrite with the current timestamp for use
        # in sorting observations. This is not perfectly reliable in a
        # distributed setting, but is good enough.
        observation.run_start = self._state.start_time
        # "arguments" duplicates part of the call repr in "representation".
        # We don't use this for anything, and it can be substantial in size, so
        # drop it.
        observation.arguments = {}
        # TODO this is a real type error, we need to unify the Branch namedtuple
        # with the real usages of `behaviors` here
        behaviors: Set[Behavior] = self._state.branches | (  # type: ignore
            # include |event| and |target| as pseudo-branch behaviors.
            bucket_features(observation.features)
        )
        # there are multiple reasons why we might queue for stability. We
        # consolidate them all into a single re-execution.
        queue_for_stability = set()

        status = observation.metadata.data_status
        if status is not Status.INTERESTING and self._state.priority in [
            QueuePriority.FAILURE_SHRUNK,
            QueuePriority.FAILURE_UNSHRUNK,
            QueuePriority.FAILURE_FIXED,
        ]:
            failure_observation = self._state.extra_queue_data
            assert failure_observation is not None
            assert isinstance(failure_observation, Observation)
            state = {
                QueuePriority.FAILURE_SHRUNK: FailureState.SHRUNK,
                QueuePriority.FAILURE_UNSHRUNK: FailureState.UNSHRUNK,
                QueuePriority.FAILURE_FIXED: FailureState.FIXED,
            }[self._state.priority]
            self.downgrade_failure(
                self._state.choices, failure_observation, state=state
            )

        behaviors_before = len(self.corpus.behavior_counts)
        fingerprints_before = len(self.corpus.fingerprints)
        new_behavior = False
        new_fingerprint = False
        coverage_observation = observation
        # only add coverage from stable re-executions.
        # TODO if only *some* of the behaviors/fingerprints are stable,
        # we want to add just those, rather than discarding the entire
        # coverage set if anything doesn't match.
        consider_corpus_coverage = False
        if self._state.priority is QueuePriority.STABILITY:
            assert self._state.extra_queue_data is not None
            if "covering" in self._state.extra_queue_data["reasons"]:
                if (
                    behaviors == self._state.extra_queue_data["behaviors"]
                    and observation.metadata.data_status is Status.VALID
                ):
                    # make sure to save the observation from the original execution,
                    # not the re-execution. The re-execution is just to make sure the
                    # coverage is not flaky. Everything else should use the original
                    # execution.
                    coverage_observation = self._state.extra_queue_data["observation"]
                    consider_corpus_coverage = True
            if "observation" in self._state.extra_queue_data["reasons"]:
                self._save_observation(
                    # Use the observation from the original execution, not this
                    # re-execution. The re-execution is just to check for stability.
                    self._state.extra_queue_data["observation"],
                    stability=(
                        Stability.STABLE
                        if behaviors == self._state.extra_queue_data["behaviors"]
                        else Stability.UNSTABLE
                    ),
                )
                self._time_in_observation_stability += elapsed_time

        elif self.corpus.would_change_coverage(behaviors, observation=observation):
            # if the replay has the same behaviors and fingerprint,
            # add to corpus on that iteration. if unstable, enqueue again to determine
            # stable vs pseudostable vs unstable (due to caching behavior etc).
            # don't add coverage to the corpus this time around. We'll do that when
            # re-executing for stability.
            queue_for_stability.add("covering")

        if consider_corpus_coverage:
            assert coverage_observation.metadata.choice_nodes is not None
            choices = tuple(n.value for n in coverage_observation.metadata.choice_nodes)
            self.corpus.consider_coverage(
                behaviors,
                observation=coverage_observation,
                # don't save observations for choices we loaded from the database
                # corpus or failures. Observations are nondeterministic,
                # (via `run_start`, but also `timing`), and will end up
                # duplicating observations here.
                save_observation=Choices(choices) not in self._loaded_for_replay,
            )
            new_behavior = behaviors_before != len(self.corpus.behavior_counts)
            new_fingerprint = fingerprints_before != len(self.corpus.fingerprints)
            if new_behavior:
                self.since_new_behavior = 0
            if new_fingerprint:
                self.since_new_fingerprint = 0

        # always consider executions for failures in the corpus, regardless of
        # stability status / replaying for stability. We still want to report
        # flaky / unstable failures, unlike flaky / unstable coverage.
        self.corpus.consider_failure(observation)

        self.elapsed_time += elapsed_time
        self.status_counts[status] += 1
        if self._state.priority is None:
            # this was a "useful" / mutated / not-replayed-from-a-queue input.
            self.elapsed_time_mutated += elapsed_time
            self.status_counts_mutated[status] += 1
            # we only count new coverage when executing for stability, in which
            # case priority would be QueuePriority.STABILITY. This means that
            # our metrics are one input behind in the stable case, but also that
            # we don't reset to 0 in the unstable case.
            assert not new_behavior
            assert not new_fingerprint
            self.since_new_behavior += 1
            self.since_new_fingerprint += 1
            # we only consider corpus coverage in ReplayPriority.STABILITY
            assert not consider_corpus_coverage
            if (
                not self.corpus.would_change_coverage(
                    behaviors, observation=observation
                )
                and observation.metadata.data_status >= Status.VALID
            ):
                # * If an input had new or improved coverage, then it was already
                #   considered for coverage, which already update behavior counts.
                #   (we have to update behavior counts when adding coverage, so
                #   that clearing behavior_counts maintains the correct keys).
                # * If an input does not have new or improved coverage, then we
                #   still want to update the behavior counts for the observed
                #   behaviors. We do so here.
                assert behaviors <= set(self.corpus.behavior_counts)
                self.corpus.behavior_counts.update(behaviors)

            assert self.elapsed_time_mutated <= self.elapsed_time
            assert self.status_counts_mutated <= self.status_counts

        if new_behavior or new_fingerprint:
            self._save_report(self._report)
        elif _should_save_timed_report(self.elapsed_time, self._last_saved_report_at):
            report = self._report
            self._save_report(report)
            self._last_timed_report = report

        if self._state.save_rolling_observation:
            if self._state.rolling_observation_stability:
                # we don't save the observation yet. we do that once we know whether
                # it's stable or not on the reexecution.
                queue_for_stability.add("observation")
            else:
                # if we aren't re-executing for stability, for instance because
                # we've gone over overhead cap for observation stability, we
                # instead save an observation without re-executing, with an
                # unknown stability status.
                self._save_observation(observation, stability=None)

        if queue_for_stability:
            self._enqueue(
                QueuePriority.STABILITY,
                choices=tuple(n.value for n in observation.metadata.choice_nodes),
                extra_data={
                    "observation": observation,
                    "behaviors": behaviors,
                    "reasons": queue_for_stability,
                },
            )

        self._state = None

    def _fresh_choice(
        self, choice_type: ChoiceTypeT, constraints: ChoiceConstraintsT
    ) -> ChoiceT:
        return fresh_choice(choice_type, constraints, random=self.random)

    def _pop_choice(
        self, choice_type: ChoiceTypeT, constraints: ChoiceConstraintsT
    ) -> ChoiceT:
        assert self._state is not None
        if self._state.choice_index >= len(self._state.choices):
            # past our prefix. draw a random choice
            return self._fresh_choice(choice_type, constraints)

        choice = self._state.choices[self._state.choice_index]
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

        self._state.choice_index += 1
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
