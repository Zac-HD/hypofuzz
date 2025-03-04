"""Adaptive fuzzing for property-based tests using Hypothesis."""

import abc
import enum
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from random import Random
from typing import TYPE_CHECKING, Optional, Union

from hypothesis import __version__ as hypothesis_version, settings
from hypothesis.core import encode_failure
from hypothesis.database import ExampleDatabase, choices_from_bytes, choices_to_bytes
from hypothesis.internal.conjecture.choice import ChoiceNode, ChoiceT, choices_key
from hypothesis.internal.conjecture.data import (
    ConjectureData,
    ConjectureResult,
    Status,
    _Overrun,
)
from hypothesis.internal.conjecture.engine import ConjectureRunner
from hypothesis.internal.conjecture.shrinker import Shrinker, sort_key as _sort_key
from hypothesis.internal.escalation import InterestingOrigin
from sortedcontainers import SortedDict

from hypofuzz.coverage import Arc

if TYPE_CHECKING:
    from typing import TypeAlias

ChoicesT: "TypeAlias" = tuple[ChoiceT, ...]
NodesT: "TypeAlias" = tuple[ChoiceNode, ...]


class Choices:
    """
    A wrapper around e.g. data.choices, suitable for hash-based comparisons as
    in sets or dict keys.
    """

    def __init__(self, choices: ChoicesT) -> None:
        self.choices = choices

    def __hash__(self) -> int:
        return hash(choices_key(self.choices))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Choices):
            return NotImplemented
        return choices_key(self.choices) == choices_key(other.choices)

    def __str__(self) -> str:
        return f"Choices({self.choices!r})"

    __repr__ = __str__

    def __len__(self) -> int:
        return len(self.choices)

    def __iter__(self) -> Iterator[ChoiceT]:
        return iter(self.choices)

    def __getitem__(self, i: int) -> ChoiceT:
        return self.choices[i]


class HowGenerated(enum.Enum):
    blackbox = "blackbox"
    mutation = "mutation"
    shrinking = "shrinking"


def sort_key(nodes: Union[NodesT, ConjectureResult]) -> tuple[int, tuple[int, ...]]:
    """Sort choice nodes in shortlex order.

    See `hypothesis.internal.conjecture.engine.sort_key` for details on why we
    use shortlex order in particular.  This tweaked version is identical except
    for handling ConjectureResult objects too.
    """
    if isinstance(nodes, ConjectureResult):
        nodes = nodes.nodes
    return _sort_key(nodes)


def reproduction_decorator(choices: ChoicesT) -> str:
    """Return `@reproduce_failure` decorator for the given choices."""
    return f"@reproduce_failure({hypothesis_version!r}, {encode_failure(choices)!r})"


def get_shrinker(
    pool: "Pool",
    fn: Callable[[ConjectureData], None],
    *,
    initial: Union[ConjectureData, ConjectureResult],
    predicate: Callable[..., bool],
    random: Random,
    explain: bool = False,
) -> Shrinker:
    s = settings(database=pool._database, deadline=None)
    return Shrinker(
        ConjectureRunner(fn, random=random, database_key=pool._key, settings=s),
        initial=initial,
        predicate=predicate,
        allow_transition=None,
        explain=explain,
    )


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
        self.results: dict[NodesT, ConjectureResult] = SortedDict(sort_key)

        # For each arc, what's the minimal covering example?
        self.covering_nodes: dict[Arc, NodesT] = {}
        # How many times have we seen each arc since discovering our latest arc?
        self.arc_counts: Counter[Arc] = Counter()

        # And various internal attributes and metadata
        self.interesting_examples: dict[
            InterestingOrigin, tuple[ConjectureResult, list[str]]
        ] = {}
        self._loaded_from_database: set[Choices] = set()
        self.__shrunk_to_nodes: set[NodesT] = set()

        # To show the current state of the pool in the dashboard
        self.json_report: list[list[str]] = []
        self._in_distill_phase = False

    def __repr__(self) -> str:
        rs = {b: r.extra_information.branches for b, r in self.results.items()}  # type: ignore
        return (
            f"<Pool\n    results={rs}\n    arc_counts={self.arc_counts}\n    "
            f"covering_nodes={self.covering_nodes}\n>"
        )

    def _check_invariants(self) -> None:
        """Check all invariants of the structure."""
        seen: set[Arc] = set()
        for res in self.results.values():
            # Each result in our ordered choices covers at least one arc not covered
            # by any more-minimal result.
            not_previously_covered = res.extra_information.branches - seen  # type: ignore
            assert not_previously_covered
            # And our covering_choices map points back the correct (minimal) choices
            for arc in not_previously_covered:
                assert self.covering_nodes[arc] == res.nodes
            seen.update(res.extra_information.branches)  # type: ignore

        # And the union of those branches is exactly covered by our counters.
        assert seen == set(self.covering_nodes), seen.symmetric_difference(
            self.covering_nodes
        )
        assert seen == set(self.covering_nodes), seen.symmetric_difference(
            self.arc_counts
        )

        # Every covering choice was either read from the database, or saved to it.
        covering_choices = {
            Choices(tuple(node.value for node in nodes))
            for nodes in self.covering_nodes.values()
        }
        assert self._loaded_from_database.issuperset(covering_choices)

    @property
    def _fuzz_key(self) -> bytes:
        return self._key + b".fuzz"

    def add(
        self, result: Union[ConjectureResult, _Overrun], source: HowGenerated
    ) -> Optional[bool]:
        """Update the corpus with the result of running a test.

        Returns None for invalid examples, False if no change, True if changed.
        """
        if result.status < Status.VALID:
            return None
        assert isinstance(result, ConjectureResult)

        assert result.extra_information is not None
        # We now know that we have a ConjectureResult representing a valid test
        # execution, either passing or possibly failing.
        branches = result.extra_information.branches  # type: ignore
        nodes = result.nodes

        # If the example is "interesting", i.e. the test failed, add the choices to
        # the database under Hypothesis' default key so it will be reproduced.
        if result.status == Status.INTERESTING:
            origin = result.interesting_origin
            assert origin is not None
            if origin not in self.interesting_examples or (
                sort_key(result) < sort_key(self.interesting_examples[origin][0])
            ):
                self._database.save(self._key, choices_to_bytes(result.choices))
                self.interesting_examples[origin] = (
                    result,
                    [
                        getattr(result.extra_information, "call_repr", "<unknown>"),
                        result.extra_information.reports,  # type: ignore
                        reproduction_decorator(result.choices),
                        result.extra_information.traceback,  # type: ignore
                    ],
                )
                return True

        # If we haven't just discovered new branches and our example is larger than the
        # current largest minimal example, we can skip the expensive calculation.
        if (not branches.issubset(self.arc_counts)) or (
            self.results
            and sort_key(result.nodes)
            < sort_key(self.results.keys()[-1])  # type: ignore
            and any(
                sort_key(nodes) < sort_key(known_nodes)
                for arc, known_nodes in self.covering_nodes.items()
                if arc in branches
            )
        ):
            # We do this the stupid-but-obviously-correct way: add the new choices to
            # our tracked corpus, and then run a distillation step.
            self.results[result.nodes] = result
            self._database.save(self._fuzz_key, choices_to_bytes(result.choices))
            self._loaded_from_database.add(Choices(result.choices))
            # Clear out any redundant entries
            seen_branches: set[Arc] = set()
            self.covering_nodes = {}
            for res in list(self.results.values()):
                assert res.extra_information is not None
                covers = res.extra_information.branches - seen_branches  # type: ignore
                seen_branches.update(res.extra_information.branches)  # type: ignore
                if not covers:
                    del self.results[res.nodes]
                    self._database.delete(self._fuzz_key, choices_to_bytes(res.choices))
                else:
                    for arc in covers:
                        self.covering_nodes[arc] = res.nodes
            # We add newly-discovered branches to the counter later; so here our only
            # unseen branches should be the newly discovered branches.
            assert seen_branches - set(self.arc_counts) == branches - set(
                self.arc_counts
            )
            self.json_report = [
                [
                    reproduction_decorator(res.choices),
                    getattr(res.extra_information, "call_repr", "<unknown>"),
                    res.extra_information.reports,  # type: ignore
                ]
                for res in self.results.values()
            ]

        # Either update the arc counts so we can prioritize rarer branches in future,
        # or save an example with new coverage and reset the counter because we'll
        # have a different distribution with a new seed pool.
        if branches.issubset(self.arc_counts):
            self.arc_counts.update(branches)
        else:
            # Reset our seen arc counts.  This is essential because changing our
            # seed pool alters the probability of seeing each arc in future.
            # For details see AFL-fast, esp. the markov-chain trick.
            self.arc_counts = Counter(branches.union(self.arc_counts))

            # Save this choices as our minimal-known covering example for each new arc.
            if result.nodes not in self.results:
                self.results[result.nodes] = result
            self._database.save(self._fuzz_key, choices_to_bytes(result.choices))
            for arc in branches - set(self.covering_nodes):
                self.covering_nodes[arc] = nodes

            # We've just finished making some tricky changes, so this is a good time
            # to assert that all our invariants have been upheld.
            self._check_invariants()
            return True

        return False

    def _choices_for_key(self, key: bytes) -> set[Choices]:
        return {
            Choices(choices)
            for b in self._database.fetch(key)
            if (choices := choices_from_bytes(b)) is not None
        }

    def fetch(self) -> Iterable[ChoicesT]:
        """Yield all choice sequences from the database which have not been loaded before.

        For the purposes of this method, a choice sequence which we saved to the database
        counts as having been loaded - the idea is to avoid duplicate executions.
        """
        # TODO: hypothesis uses the bare key only for minimal failing examples;
        #       we should use the secondary key for unshrunk examples and then
        #       also the .fuzz key for covering examples.
        #
        # Also: consider distinguishing between covers-branch and coverage-fingerprint,
        #       and between minimal and other examples.  The fingerprint (set of
        #       branches) isn't currently used because our concept of "branch" is
        #       too large; should only include interesting files + skip branchless
        #       lines of code to keep the size manageable.
        saved = sorted(
            self._choices_for_key(self._key) - self._loaded_from_database,
            key=len,
            reverse=True,
        )
        self._loaded_from_database.update(saved)
        for idx in (0, -1):
            if saved:
                yield saved.pop(idx).choices
        seeds = sorted(
            self._choices_for_key(self._key + b".fuzz") - self._loaded_from_database,
            key=len,
            reverse=True,
        )
        self._loaded_from_database.update(seeds)
        yield from (choices.choices for choices in seeds)
        yield from (choices.choices for choices in saved)
        self._check_invariants()

    def distill(self, fn: Callable[[ConjectureData], None], random: Random) -> None:
        """Shrink to a pool of *minimal* covering examples.

        We have a couple of unusual structures here.

        1. We exploit the fact that each successful shrink calls self.add(result)
           to let us skip a lot of work.  Because any "fully shrunk" example is
           a local fixpoint of all our reduction passes, there's no point trying
           to shrink a choice sequence for arc A if it's already minimal for arc B.
           (because we'd have updated the best known for A while shrinking for B)
        2. All of the loops are designed to make some amount of progress, and then
           try again if they did not reach a fixpoint.  Almost all of the structures
           we're using can be mutated in the process, so it can get strange.
        """
        self._in_distill_phase = True
        self._check_invariants()
        minimal_branches = {
            arc
            for arc, nodes in self.covering_nodes.items()
            if nodes in self.__shrunk_to_nodes
        }
        while set(self.covering_nodes) - minimal_branches:
            # The "largest first" shrinking order is designed to maximise the rate
            # of incidental progress, where shrinking hard problems stumbles over
            # smaller starting points for the easy ones.
            arc_to_shrink = max(
                set(self.covering_nodes) - minimal_branches,
                key=lambda a: sort_key(self.covering_nodes[a]),
            )
            shrinker = get_shrinker(
                self,
                fn,
                initial=self.results[self.covering_nodes[arc_to_shrink]],
                predicate=lambda d, a=arc_to_shrink: a in d.extra_information.branches,
                random=random,
            )
            shrinker.shrink()
            self.__shrunk_to_nodes.add(shrinker.shrink_target.nodes)
            minimal_branches |= {
                arc
                for arc, choices in self.covering_nodes.items()
                if choices == shrinker.shrink_target.choices
            }
            self._check_invariants()
        self._in_distill_phase = False


class Mutator(abc.ABC):
    def __init__(self, pool: Pool, random: Random) -> None:
        self.pool = pool
        self.random = random

    @abc.abstractmethod
    def generate_choices(self) -> ChoicesT:
        """Generate a choice sequence, usually by choosing and mutating examples from pool."""
        raise NotImplementedError


class BlackBoxMutator(Mutator):
    def generate_choices(self) -> ChoicesT:
        """Return an empty prefix, triggering blackbox random generation.

        This 'null mutator' is sometimes useful because - doing no work - it's very
        fast, and it provides a good baseline for comparisons.
        """
        return ()


class CrossOverMutator(Mutator):
    def _get_weights(self) -> list[float]:
        # (1 / rarest_arc_count) each item in self.results
        # This is related to the AFL-fast trick, but doesn't track the transition
        # probabilities - just node densities in the markov chain.
        weights = [
            1 / min(self.pool.arc_counts[arc] for arc in res.extra_information.branches)  # type: ignore
            for res in self.pool.results.values()
        ]
        total = sum(weights)
        return [x / total for x in weights]

    def generate_choices(self) -> ChoicesT:
        """Splice together two known valid choice sequences.

        This is a pretty poor mutator, and not structure-aware, but works better than
        the blackbox one already.
        """
        if not self.pool.results:
            return ()
        # Choose two previously-seen choice sequences to form a prefix and postfix,
        # plus some random bytes in the middle to pad it out a bit.
        # TODO: exploit the .examples tracking for structured mutation.
        choices = self.random.choices(
            list(self.pool.results.values()), weights=self._get_weights(), k=2
        )
        prefix = choices[0].choices
        suffix = choices[1].choices
        # TODO: structure-aware slicing - we want to align the crossover points
        # with a `start_example()` boundary.  This is tricky to get out of Hypothesis
        # at the moment though, and we don't have any facilities (beyond luck!)
        # to line up the postfix boundary correctly.  Requires upstream changes.
        return (
            prefix[: self.random.randint(0, len(prefix))]
            + suffix[: self.random.randint(0, len(suffix))]
        )


class RadamsaMutator(Mutator):
    # TODO: based on https://github.com/tsundokul/pyradamsa
    # I *expect* this to be useful mostly for evaluation, and I'd rather not
    # have the dependency, but I guess it could surprise me.
    # (expectation/evaluation is to quantify the advantages of structure-aware
    # mutation given Hypothesis' designed-for-that IR format)
    pass
