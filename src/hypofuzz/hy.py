"""Adaptive fuzzing for property-based tests using Hypothesis."""

import contextlib
import itertools
import sys
import traceback
from random import Random
from typing import Callable, Generator, NoReturn, Set

from hypothesis import strategies as st
from hypothesis.core import (
    BuildContext,
    deterministic_PRNG,
    failure_exceptions_to_catch,
    get_trimmed_traceback,
    skip_exceptions_to_reraise,
)
from hypothesis.errors import StopTest, UnsatisfiedAssumption
from hypothesis.internal.conjecture.data import ConjectureData, ConjectureResult, Status
from hypothesis.internal.conjecture.engine import BUFFER_SIZE
from hypothesis.internal.conjecture.junkdrawer import stack_depth_of_caller

from .cov import Arc, CollectionContext


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
        data.freeze()
        buf = (yield data.as_result()) or b""
    raise NotImplementedError("Loop not expected to exit")


def coverage_fuzzer(
    test: Callable[..., None], **kwargs: st.SearchStrategy
) -> Generator[ConjectureResult, ConjectureData, NoReturn]:
    """Wrap the user's test function into a minimal Conjecture fuzz target.

    This is a combination of the logic in StateForAGivenExecution in
    hypothesis.core, and hypothesis.internal.conjecture.engine.ConjectureRunner
    with as much as possible taken out - for this fuzzing mode we prioritize
    performance over health-checks (just run Hypothesis for the latter!).
    """
    collector = CollectionContext()

    gen = fuzz_in_generator(
        test,
        strategy=st.tuples(st.just(()), st.fixed_dictionaries(kwargs)),
        collector=collector,
    )

    # We ignore branches that were covered by the minimal example
    next(gen)
    yield gen.send(b"")
    arcs_for_minimal_example = collector.arcs
    seen: Set[Arc] = set()
    last_new_cov_at = 0
    for i in itertools.count():
        next(gen)
        result = gen.send(b"")
        yield result
        novel = arcs_for_minimal_example.symmetric_difference(collector.arcs) - seen
        if novel:
            msg = f"i={i}, since={i - last_new_cov_at}, new={len(novel)}"
            print(msg, flush=True)  # noqa
            last_new_cov_at = i
            seen |= novel
    raise NotImplementedError("Loop not expected to exit")
