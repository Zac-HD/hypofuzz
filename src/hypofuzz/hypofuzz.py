"""Adaptive fuzzing for property-based tests using Hypothesis."""

import contextlib
import inspect
import os
import platform
import socket
import subprocess
import sys
import time
import traceback
from base64 import b64encode
from collections.abc import Callable, Generator
from contextlib import suppress
from functools import lru_cache
from pathlib import Path
from random import Random
from typing import Any, Optional, Union
from uuid import uuid4

import hypothesis
from hypothesis import settings
from hypothesis.control import BuildContext
from hypothesis.core import (
    Stuff,
    failure_exceptions_to_catch,
    process_arguments_to_given,
)
from hypothesis.database import ExampleDatabase
from hypothesis.errors import StopTest, UnsatisfiedAssumption
from hypothesis.internal.conjecture.choice import ChoiceT, ChoiceTemplate
from hypothesis.internal.conjecture.data import (
    ConjectureData,
    ConjectureResult,
    Status,
    _Overrun,
)
from hypothesis.internal.conjecture.engine import RunIsComplete
from hypothesis.internal.conjecture.junkdrawer import stack_depth_of_caller
from hypothesis.internal.entropy import deterministic_PRNG
from hypothesis.internal.escalation import InterestingOrigin, get_trimmed_traceback
from hypothesis.internal.reflection import function_digest, get_signature
from hypothesis.reporting import with_reporter
from hypothesis.vendor.pretty import RepresentationPrinter

import hypofuzz
from hypofuzz.corpus import (
    BlackBoxMutator,
    CrossOverMutator,
    HowGenerated,
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

process_uuid = uuid4().hex


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
        f"{depth} here, but we are already much deeper than expected.  Aborting "
        "now, to avoid extending the stack limit in an infinite loop..."
    )
    try:
        sys.setrecursionlimit(depth + recursion_limit)
        yield
    finally:
        sys.setrecursionlimit(recursion_limit)


class HitShrinkTimeoutError(Exception):
    pass


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
    ) -> None:
        """Construct a FuzzProcess from specific arguments."""
        # The actual fuzzer implementation
        self.random = Random(random_seed)
        self._test_fn = test_fn
        self._stuff = stuff
        self.nodeid = nodeid or test_fn.__qualname__
        self.database_key = database_key

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
        source: HowGenerated = HowGenerated.shrinking,
        collector: Optional[contextlib.AbstractContextManager] = None,
    ) -> Union[ConjectureResult, _Overrun]:
        """Run the test_fn on a given data, in a way a Shrinker can handle.

        In normal operation, it's called via run_one (above), but we might also
        delegate to the shrinker to find minimal covering examples.
        """
        start = time.perf_counter()
        self.ninputs += 1
        collector = collector or CoverageCollectionContext()
        assert collector is not None
        reports: list[object] = []
        try:
            with (
                deterministic_PRNG(),
                BuildContext(data, is_final=True) as context,
                constant_stack_depth(),
                with_reporter(reports.append),
            ):
                # Note that the data generation and test execution happen in the same
                # coverage context.  We may later split this, or tag each separately.
                with collector:
                    if self._stuff.selfy is not None:
                        data.hypothesis_runner = self._stuff.selfy  # type: ignore
                    # Generate all arguments to the test function.
                    args = self._stuff.args
                    kwargs = dict(self._stuff.kwargs)
                    kw, argslices = context.prep_args_kwargs_from_strategies(
                        self._stuff.given_kwargs
                    )
                    kwargs.update(kw)

                    printer = RepresentationPrinter(context=context)
                    printer.repr_call(
                        self._test_fn.__name__,
                        args,
                        kwargs,
                        force_split=True,
                        arg_slices=argslices,
                        leading_comment=(
                            "# " + context.data.slice_comments[(0, 0)]
                            if (0, 0) in context.data.slice_comments
                            else None
                        ),
                    )
                    data.extra_information.call_repr = printer.getvalue()  # type: ignore

                    self._test_fn(*args, **kwargs)
        except StopTest:
            data.status = Status.OVERRUN
        except UnsatisfiedAssumption:
            data.status = Status.INVALID
        except failure_exceptions_to_catch() as e:
            data.status = Status.INTERESTING
            tb = get_trimmed_traceback()
            data.interesting_origin = InterestingOrigin.from_exception(e)
            data.extra_information.traceback = "".join(  # type: ignore
                traceback.format_exception(type(e), value=e, tb=tb)
            )
        except KeyboardInterrupt:
            # If you have a test function which raises KI, this is pretty useful.
            print(f"Got a KeyboardInterrupt in {self.nodeid}, exiting...")
            raise
        finally:
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
        if self.pool.add(data.as_result(), source):
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
    with suppress(Exception), open("/proc/self/cgroup") as f:
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
