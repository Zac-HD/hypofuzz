"""Adaptive fuzzing for property-based tests using Hypothesis."""

import contextlib
import itertools
import sys
import time
import traceback
from inspect import getfullargspec
from random import Random
from typing import Any, Callable, Dict, Generator, List, NoReturn, Union

from hypothesis import strategies as st
from hypothesis.core import (
    BuildContext,
    deterministic_PRNG,
    failure_exceptions_to_catch,
    get_trimmed_traceback,
    process_arguments_to_given,
    skip_exceptions_to_reraise,
)
from hypothesis.database import ExampleDatabase
from hypothesis.errors import StopTest, UnsatisfiedAssumption
from hypothesis.internal.conjecture.data import ConjectureData, ConjectureResult, Status
from hypothesis.internal.conjecture.engine import BUFFER_SIZE
from hypothesis.internal.conjecture.junkdrawer import stack_depth_of_caller
from hypothesis.internal.reflection import function_digest
from sortedcontainers import SortedKeyList

from .corpus import BlackBoxMutator, CrossOverMutator, Pool
from .cov import CollectionContext

Report = Dict[str, Union[int, float, str]]


@contextlib.contextmanager
def constant_stack_depth() -> Generator[None, None, None]:
    # TODO: consider extracting this upstream so we can just import it.
    recursion_limit = sys.getrecursionlimit()
    depth = stack_depth_of_caller()
    # Because we add to the recursion limit, to be good citizens we also add
    # a check for unbounded recursion.  The default limit is 1000, so this can
    # only ever trigger if something really strange is happening and it's hard
    # to imagine an intentionally-deeply-recursive use of this code.
    assert depth <= 1000, (
        f"Hypothesis would usually add {recursion_limit} to the stack depth of "
        "{depth} here, but we are already much deeper than expected.  Aborting "
        "now, to avoid extending the stack limit in an infinite loop..."
    )
    try:
        sys.setrecursionlimit(depth + recursion_limit)
        yield
    finally:
        sys.setrecursionlimit(recursion_limit)


def fuzz_in_generator(
    test: Callable[..., None],
    strategy: st.SearchStrategy,
    collector: CollectionContext = None,
    random: Random = None,
) -> Generator[ConjectureResult, bytes, NoReturn]:
    """Wrap the user's test function into a minimal Conjecture fuzz target.

    This is our main integration point with Hypothesis internals - and it's designed
    so that we can get a ConjectureResult out, push a bytestring in, and be done.
    This is very useful in that it provides a great baseline for evaluations.

    It's a combination of the logic in StateForAGivenExecution in
    hypothesis.core, and hypothesis.internal.conjecture.engine.ConjectureRunner
    with as much as possible taken out - for this fuzzing mode we prioritize
    performance over health-checks (just run Hypothesis for the latter!).
    """
    random = random or Random(0)
    collector = collector or contextlib.nullcontext()  # type: ignore
    buf = b"\0" * BUFFER_SIZE
    while True:
        data = ConjectureData(max_length=BUFFER_SIZE, prefix=buf, random=random)
        try:
            with deterministic_PRNG(), BuildContext(data), constant_stack_depth():
                # Note that the data generation and test execution happen in the same
                # coverage context.  We may later split this, or tag each separately.
                with collector:
                    args, kwargs = data.draw(strategy)
                    test(*args, **kwargs)
        except StopTest:
            data.status = Status.OVERRUN
        except (UnsatisfiedAssumption,) + skip_exceptions_to_reraise():
            data.status = Status.INVALID
        except failure_exceptions_to_catch() as e:
            data.status = Status.INTERESTING
            tb = get_trimmed_traceback()
            filename, lineno, *_ = traceback.extract_tb(tb)[-1]
            data.interesting_origin = (type(e), filename, lineno)
            data.note(e)
        data.extra_information.arcs = frozenset(getattr(collector, "arcs", ()))
        data.freeze()
        buf = (yield data.as_result()) or b""
    raise NotImplementedError("Loop not expected to exit")


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
        nodeid: str = None,
        extra_kw: Dict[str, object] = None,
    ) -> "FuzzProcess":
        """Return a FuzzProcess for an @given-decorated test function."""
        _, _, _, search_strategy = process_arguments_to_given(
            wrapped_test,
            arguments=(),
            kwargs=extra_kw,
            given_kwargs=wrapped_test.hypothesis._given_kwargs,
            argspec=getfullargspec(wrapped_test),
        )
        return cls(
            test_fn=wrapped_test.hypothesis.inner_test,
            strategy=search_strategy,
            nodeid=nodeid,
            database_key=function_digest(wrapped_test),
            hypothesis_database=wrapped_test._hypothesis_internal_use_settings.database,
        )

    def __init__(
        self,
        test_fn: Callable,
        strategy: st.SearchStrategy,
        *,
        random_seed: int = 0,
        nodeid: str = None,
        database_key: bytes,
        hypothesis_database: ExampleDatabase,
    ) -> None:
        """Construct a FuzzProcess from specific arguments."""
        # The actual fuzzer implementation
        self.random = Random(random_seed)
        self.__test_fn = test_fn
        self.__strategy = strategy
        self.nodeid = nodeid or test_fn.__qualname__

        # The seed pool is responsible for managing all seed state, including saving
        # novel seeds to the database.  This includes tracking how often each branch
        # has been hit, minimal covering examples, and so on.
        self.pool = Pool(hypothesis_database, database_key)
        self._mutator_blackbox = BlackBoxMutator(self.pool, self.random)
        self._mutator_crossover = CrossOverMutator(self.pool, self.random)

        # Set up the basic data that we'll track while fuzzing
        self.ninputs = 0
        self.elapsed_time = 0.0
        self.since_new_cov = 0
        # Any new examples from the database will be added to this replay buffer
        self._replay_buffer: List[bytes] = []

        # We batch updates, since frequent HTTP posts are slow
        self._to_post: List[Report] = []
        self._last_post_time = self.elapsed_time

    def startup(self) -> None:
        """Set up initial state and prepare to replay the saved behaviour."""
        assert self.ninputs == 0, "already started this FuzzProcess"
        # Report that we've started this fuzz target, and run zero examples so far
        self._report_change(self._json_description)
        # Next, restore progress made in previous runs by loading our saved examples.
        # This is meant to be the minimal set of inputs that exhibits all distinct
        # behaviours we've observed to date.  Replaying takes longer than restoring
        # our data structures directly, but copes much better with changed behaviour.
        self._replay_buffer.extend(self.pool.fetch())
        self._replay_buffer.append(b"\x00" * BUFFER_SIZE)

    def generate_prefix(self) -> bytes:
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
        if self._replay_buffer:
            return self._replay_buffer.pop()

        # TODO: currently hard-coding a particular mutator; we want to do MOpt-style
        # adaptive weighting of all the different mutators we could use.
        # For now though, we'll just use a hardcoded swapover point
        if self.since_new_cov < 1000 and self.ninputs < 100_000:
            return self._mutator_blackbox.generate_buffer()
        return self._mutator_crossover.generate_buffer()

    def run_one(self) -> None:
        """Run a single input through the fuzz target."""
        start = time.perf_counter()
        self.ninputs += 1

        # If we've been stable for a little while, try loading new examples from the
        # database.  We do this unconditionally because even if this fuzzer doesn't
        # know of other concurrent runs, there may be e.g. a test process sharing the
        # database.  We do make it infrequent to manage the overhead though.
        if self.ninputs % 1000 == 0 and self.since_new_cov > 1000:
            self._replay_buffer.extend(self.pool.fetch())

        # Run the input
        collector = CollectionContext()
        data = ConjectureData(
            max_length=BUFFER_SIZE,
            prefix=self.generate_prefix(),
            random=self.random,
        )
        try:
            with deterministic_PRNG(), BuildContext(data), constant_stack_depth():
                # Note that the data generation and test execution happen in the same
                # coverage context.  We may later split this, or tag each separately.
                with collector:
                    args, kwargs = data.draw(self.__strategy)
                    self.__test_fn(*args, **kwargs)
        except StopTest:
            data.status = Status.OVERRUN
        except UnsatisfiedAssumption:
            data.status = Status.INVALID
        except failure_exceptions_to_catch() as e:
            data.status = Status.INTERESTING
            tb = get_trimmed_traceback()
            filename, lineno, *_ = traceback.extract_tb(tb)[-1]
            data.interesting_origin = (type(e), filename, lineno)
            data.note(e)

        # In addition to coverage arcs, use psudeo-coverage information provided via
        # the `hypothesis.event()` function - exploiting user-defined partitions
        # designed for diagnostic output to guide generation.  See
        # https://hypothesis.readthedocs.io/en/latest/details.html#hypothesis.event
        data.extra_information.arcs = frozenset(getattr(collector, "arcs", ())).union(
            (event_str, 0, 0)
            for event_str in map(str, data.events)
            if not event_str.startswith("Retried draw from ")
            or event_str.startswith("Aborted test because unable to satisfy ")
        )

        data.freeze()
        # Update the pool and report any changes immediately for new coverage.  If no
        # new coverage, occasionally send an update anyway so we don't look stalled.
        if self.pool.add(data.as_result()):
            self.since_new_cov = 0
        else:
            self.since_new_cov += 1
        if 0 in (self.since_new_cov, self.ninputs % 100):
            self._to_post.append(self._json_description)

        self.elapsed_time += time.perf_counter() - start
        if self._to_post and (
            self.has_found_failure or self._last_post_time + 10 < self.elapsed_time
        ):
            self._report_change(self._to_post)
            del self._to_post[:]

    def _report_change(self, data: Union[Report, List[Report]]) -> None:
        """Replace this method to send JSON data to the dashboard."""

    @property
    def _json_description(self) -> Dict[str, Union[str, int, float]]:
        """Summarise current state to send to dashboard."""
        if self.pool.interesting_origin is not None:
            return {
                "nodeid": self.nodeid,
                "elapsed_time": self.elapsed_time,
                "ninputs": self.ninputs,
                "arcs": len(self.pool.arc_counts),
                "note": f"raised {self.pool.interesting_origin[0].__name__}",
            }
        elif self.ninputs == 0:
            return {"nodeid": self.nodeid, "note": "starting up..."}
        return {
            "nodeid": self.nodeid,
            "elapsed_time": self.elapsed_time,
            "ninputs": self.ninputs,
            "arcs": len(self.pool.arc_counts),
            "since new cov": self.since_new_cov,
            "note": "replaying saved examples" if self._replay_buffer else "",
        }

    @property
    def has_found_failure(self) -> bool:
        """If we've already found a failing example we might reprioritize."""
        return self.pool.interesting_origin is not None


def fuzz_several(*targets_: FuzzProcess, random_seed: int = None) -> NoReturn:
    """Take N fuzz targets and run them all."""
    # TODO: this isn't actually multi-process yet, and that's bad.
    rand = Random(random_seed)
    targets = SortedKeyList(targets_, lambda t: t.since_new_cov)

    # Loop forever: at each timestep, we choose a target using an epsilon-greedy
    # strategy for simplicity (TODO: improve this later) and run it once.
    # TODO: make this aware of test runtime, so it adapts for arcs-per-second
    #       rather than arcs-per-input.
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
                print(f"found failing example for {targets[0].nodeid}")  # noqa
                targets.pop(0)
            if not targets:
                raise Exception("Found failures for all tests!")
    raise NotImplementedError("unreachable")
