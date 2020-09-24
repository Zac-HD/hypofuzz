"""Adaptive fuzzing for property-based tests using Hypothesis."""

import abc
import math
from random import Random
from typing import (
    Callable,
    Counter,
    Dict,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
)

from hypothesis import __version__ as hypothesis_version
from hypothesis.core import encode_failure
from hypothesis.database import ExampleDatabase
from hypothesis.internal.conjecture.data import (
    ConjectureData,
    ConjectureResult,
    Overrun,
    Status,
)
from hypothesis.internal.conjecture.shrinker import Shrinker
from sortedcontainers import SortedDict

from .cov import Arc


def sort_key(buffer: Union[bytes, ConjectureResult]) -> Tuple[int, bytes]:
    """Sort our buffers in shortlex order.

    See `hypothesis.internal.conjecture.shrinker.sort_key` for details on why we
    use shortlex order in particular.  This tweaked version is identical except
    for handling ConjectureResult objects too.
    """
    if isinstance(buffer, ConjectureResult):
        buffer = buffer.buffer
    return (len(buffer), buffer)


def reproduction_decorator(buffer: bytes) -> str:
    """Return `@reproduce_failure` decorator for the given buffer."""
    return f"@reproduce_failure({hypothesis_version!r}, {encode_failure(buffer)!r})"


class EngineStub:
    """A knock-off ConjectureEngine, just large enough to run a shrinker."""

    def __init__(
        self, test_fn: Callable[[bytes], ConjectureData], random: Random
    ) -> None:
        self.cached_test_function = test_fn
        self.random = random
        self.call_count = 0
        self.report_debug_info = False

    def debug(self, msg: str) -> None:
        """Unimplemented stub."""

    def explain_next_call_as(self, msg: str) -> None:
        """Unimplemented stub."""

    def clear_call_explanation(self) -> None:
        """Unimplemented stub."""


class Pool:
    """Manage the seed pool for a fuzz target.

    The class tracks the minimal valid example which covers each known arc.
    """

    def __init__(self, database: ExampleDatabase, key: bytes) -> None:
        # The database and our database key are the stable identifiers for a corpus.
        # Everything else is reconstructed each run, and tracked only in memory.
        self._database = database
        self._key = key

        # Our sorted pool of covering examples, ready to be sampled from.
        # TODO: One suggestion to reduce effective pool size/redundancy is to skip
        #       over earlier inputs whose coverage is a subset of later inputs.
        self.results: Dict[bytes, ConjectureResult] = SortedDict(sort_key)

        # For each arc, what's the minimal covering example?
        self.covering_buffers: Dict[Arc, bytes] = {}
        # How many times have we seen each arc since discovering our latest arc?
        self.arc_counts: Counter[Arc] = Counter()

        # And various internal attributes and metadata
        self.interesting_examples: Dict[
            Tuple[Type[BaseException], str, int], Tuple[ConjectureResult, List[str]]
        ] = {}
        self.__loaded_from_database: Set[bytes] = set()
        self.__shrunk_to_buffers: Set[bytes] = set()

        # To show the current state of the pool in the dashboard
        self.json_report: List[List[str]] = []

    def __repr__(self) -> str:
        rs = {b: r.extra_information.arcs for b, r in self.results.items()}
        return (
            f"<Pool\n    results={rs}\n    arc_counts={self.arc_counts}\n    "
            f"covering_buffers={self.covering_buffers}\n>"
        )

    def _check_invariants(self) -> None:
        """Check all invariants of the structure."""
        seen: Set[Arc] = set()
        for res in self.results.values():
            # Each result in our ordered buffer covers at least one arc not covered
            # by any more-minimal result.
            not_previously_covered = res.extra_information.arcs - seen
            assert not_previously_covered
            # And our covering_buffers map points back the correct (minimal) buffer
            for arc in not_previously_covered:
                assert self.covering_buffers[arc] == res.buffer
            seen.update(res.extra_information.arcs)

        # And the union of those arcs is exactly covered by our counters.
        assert seen == set(self.covering_buffers), seen.symmetric_difference(
            self.covering_buffers
        )
        assert seen == set(self.covering_buffers), seen.symmetric_difference(
            self.arc_counts
        )

        # Every covering buffer was either read from the database, or saved to it.
        assert self.__loaded_from_database.issuperset(self.covering_buffers.values())

    @property
    def _fuzz_key(self) -> bytes:
        return self._key + b".fuzz"

    @property
    def _covered_arcs(self) -> Dict[bytes, Set[Arc]]:
        out: Dict[bytes, Set[Arc]] = {}
        for arc, buf in self.covering_buffers.items():
            out.setdefault(buf, set()).add(arc)
        return out

    def add(self, result: ConjectureResult) -> Optional[bool]:
        """Update the corpus with the result of running a test.

        Returns None for invalid examples, False if no change, True if changed.
        """
        assert result is Overrun or isinstance(result, ConjectureResult), result
        if result.status < Status.VALID:
            return None

        # We now know that we have a ConjectureResult representing a valid test
        # execution, either passing or possibly failing.
        arcs = result.extra_information.arcs
        buf = result.buffer

        # If the example is "interesting", i.e. the test failed, add the buffer to
        # the database under Hypothesis' default key so it will be reproduced.
        if result.status == Status.INTERESTING:
            origin = result.interesting_origin
            if origin not in self.interesting_examples or sort_key(result) < sort_key(
                self.interesting_examples[origin]
            ):
                self.interesting_examples[origin] = (
                    result,
                    [
                        result.extra_information.call_repr,
                        result.extra_information.reports,
                        reproduction_decorator(result.buffer),
                        result.extra_information.traceback,
                    ],
                )
                return True

        # If we haven't just discovered new arcs and our example is larger than the
        # current largest minimal example, we can skip the expensive calculation.
        if (not arcs.issubset(self.arc_counts)) or (
            self.results
            and sort_key(result.buffer)
            < sort_key(self.results.keys()[-1])  # type: ignore
            and any(
                sort_key(buf) < sort_key(known_buf)
                for arc, known_buf in self.covering_buffers.items()
                if arc in arcs
            )
        ):
            # We do this the stupid-but-obviously-correct way: add the new buffer to
            # our tracked corpus, and then run a distillation step.
            self.results[result.buffer] = result
            self._database.save(self._fuzz_key, buf)
            self.__loaded_from_database.add(buf)
            # Clear out any redundant entries
            seen_arcs: Set[Arc] = set()
            self.covering_buffers = {}
            for res in list(self.results.values()):
                covers = res.extra_information.arcs - seen_arcs
                seen_arcs.update(res.extra_information.arcs)
                if not covers:
                    del self.results[res.buffer]
                    self._database.delete(self._fuzz_key, res.buffer)
                else:
                    for arc in covers:
                        self.covering_buffers[arc] = res.buffer
            # We add newly-discovered arcs to the counter later; so here our only
            # unseen arcs should be the newly discovered arcs.
            assert seen_arcs - set(self.arc_counts) == arcs - set(self.arc_counts)
            self.json_report = [
                [
                    reproduction_decorator(res.buffer),
                    res.extra_information.call_repr,
                    res.extra_information.reports,
                ]
                for res in self.results.values()
            ]

        # Either update the arc counts so we can prioritize rarer arcs in future,
        # or save an example with new coverage and reset the counter because we'll
        # have a different distribution with a new seed pool.
        if arcs.issubset(self.arc_counts):
            self.arc_counts.update(arcs)
        else:
            # Reset our seen arc counts.  This is essential because changing our
            # seed pool alters the probability of seeing each arc in future.
            # For details see AFL-fast, esp. the markov-chain trick.
            self.arc_counts = Counter(arcs.union(self.arc_counts))

            # Save this buffer as our minimal-known covering example for each new arc.
            if result.buffer not in self.results:
                self.results[result.buffer] = result
            self._database.save(self._fuzz_key, buf)
            for arc in arcs - set(self.covering_buffers):
                self.covering_buffers[arc] = buf

            # We've just finished making some tricky changes, so this is a good time
            # to assert that all our invariants have been upheld.
            self._check_invariants()
            return True

        return False

    def fetch(self) -> Iterable[bytes]:
        """Yield all buffers from the database which have not been loaded before.

        For the purposes of this method, a buffer which we saved to the database
        counts as having been loaded - the idea is to avoid duplicate executions.
        """
        saved = sorted(self._database.fetch(self._key), key=sort_key, reverse=True)
        self.__loaded_from_database.update(saved)
        for idx in (0, -1):
            if saved:
                buf = saved.pop(idx)
                yield buf
                self.__loaded_from_database.add(buf)
        seeds = sorted(
            self._database.fetch(self._key + b".fuzz"), key=sort_key, reverse=True
        )
        self.__loaded_from_database.update(seeds)
        yield from seeds
        yield from saved
        self._check_invariants()

    def distill(self, fn: Callable[[bytes], ConjectureData], random: Random) -> None:
        """Shrink to a pool of *minimal* covering examples.

        We have a couple of unusual structures here.

        1. We exploit the fact that each successful shrink calls self.add(result)
           to let us skip a lot of work.  Because any "fully shrunk" example is
           a local fixpoint of all our reduction passes, there's no point trying
           to shrink a buffer for arc A if it's already minimal for arc B.
           (because we'd have updated the best known for A while shrinking for B)
        2. All of the loops are designed to make some amount of progress, and then
           try again if they did not reach a fixpoint.  Almost all of the structures
           we're using can be mutated in the process, so it can get strange.
        """
        self._check_invariants()
        covered_arcs = self._covered_arcs
        while set(covered_arcs) - self.__shrunk_to_buffers:
            for buf in sorted(covered_arcs, key=sort_key):
                while (
                    covered_arcs[buf]
                    and buf in self.results
                    and buf not in self.__shrunk_to_buffers
                ):
                    arc_to_shrink = covered_arcs[buf].pop()
                    shrinker = Shrinker(
                        EngineStub(fn, random),
                        self.results[buf],
                        predicate=lambda d: arc_to_shrink in d.extra_information.arcs,
                        allow_transition=None,
                    )
                    shrinker.shrink()
                    self.__shrunk_to_buffers.add(shrinker.shrink_target.buffer)
            covered_arcs = self._covered_arcs
        self._check_invariants()


class Mutator(abc.ABC):
    def __init__(self, pool: Pool, random: Random) -> None:
        self.pool = pool
        self.random = random

    def _random_bytes(self, n: int) -> bytes:
        return bytes(self.random.randint(0, 255) for _ in range(n))

    @abc.abstractmethod
    def generate_buffer(self) -> bytes:
        """Generate a buffer, usually by choosing and mutating examples from pool."""
        raise NotImplementedError


class BlackBoxMutator(Mutator):
    def generate_buffer(self) -> bytes:
        """Return an empty prefix, triggering blackbox random generation.

        This 'null mutator' is sometimes useful because - doing no work - it's very
        fast, and it provides a good baseline for comparisons.
        """
        return b""


class CrossOverMutator(Mutator):
    def _get_weights(self) -> List[float]:
        # (1 / rarest_arc_count) each item in self.results
        # This is related to the AFL-fast trick, but doesn't track the transition
        # probabilities - just node densities in the markov chain.
        weights = [
            1 / min(self.pool.arc_counts[arc] for arc in res.extra_information.arcs)
            for res in self.pool.results.values()
        ]
        # Now take softmax to turn this into a probability distribution
        exp = [math.exp(x) for x in weights]
        total = sum(exp)
        return [x / total for x in exp]

    def generate_buffer(self) -> bytes:
        """Splice together two known valid buffers with some random infill.

        This is a pretty poor mutator, and not structure-aware, but works better than
        the blackbox one already.
        """
        if not self.pool.results:
            return b""
        # Choose two previously-seen buffers to form a prefix and postfix,
        # plus some random bytes in the middle to pad it out a bit.
        # TODO: exploit the .examples tracking for structured mutation.
        prefix, postfix = self.random.choices(  # type: ignore
            self.pool.results.keys(), weights=self._get_weights(), k=2  # type: ignore
        )
        buffer = (
            prefix[: self.random.randint(0, len(prefix))]
            + self._random_bytes(self.random.randint(0, 9))
            + postfix[: self.random.randint(0, len(postfix))]
        )
        assert isinstance(buffer, bytes)
        return buffer
