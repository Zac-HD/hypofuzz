"""Adaptive fuzzing for property-based tests using Hypothesis."""

import abc
import enum
import json
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
from hypofuzz.database import cov_obs_key

if TYPE_CHECKING:
    from typing import TypeAlias

ChoicesT: "TypeAlias" = tuple[ChoiceT, ...]
NodesT: "TypeAlias" = tuple[ChoiceNode, ...]
# (start, end) where start = end = (filename, line, column)
Branch: "TypeAlias" = tuple[tuple[str, int, int], tuple[str, int, int]]


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

    The class tracks the minimal valid example which covers each known branch.
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

        # For each branch, what's the minimal covering example?
        self.covering_nodes: dict[Branch, NodesT] = {}
        # How many times have we seen each branch since discovering our latest branch?
        self.branch_counts: Counter[Branch] = Counter()

        # And various internal attributes and metadata
        self.interesting_examples: dict[
            InterestingOrigin, tuple[ConjectureResult, list[str]]
        ] = {}
        self._loaded_from_database: set[Choices] = set()
        self.__shrunk_to_nodes: set[NodesT] = set()

        # To show the current state of the pool in the dashboard
        self.json_report: list[list[str]] = []

    def __repr__(self) -> str:
        rs = {b: r.extra_information.branches for b, r in self.results.items()}  # type: ignore
        return (
            f"<Pool\n    results={rs}\n    branch_counts={self.branch_counts}\n    "
            f"covering_nodes={self.covering_nodes}\n>"
        )

    def _check_invariants(self) -> None:
        """Check all invariants of the structure."""
        seen: set[Branch] = set()
        for res in self.results.values():
            # Each result in our ordered choices covers at least one branch not covered
            # by any more-minimal result.
            not_previously_covered = res.extra_information.branches - seen  # type: ignore
            assert not_previously_covered
            # And our covering_choices map points back the correct (minimal) choices
            for branch in not_previously_covered:
                assert self.covering_nodes[branch] == res.nodes
            seen.update(res.extra_information.branches)  # type: ignore

        # And the union of those branches is exactly covered by our counters.
        assert seen == set(self.covering_nodes), seen.symmetric_difference(
            self.covering_nodes
        )
        assert seen == set(self.covering_nodes), seen.symmetric_difference(
            self.branch_counts
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
        self,
        result: Union[ConjectureResult, _Overrun],
        *,
        observation: Optional[dict] = None,
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
                        getattr(result.extra_information, "string_repr", "<unknown>"),
                        result.extra_information.reports,  # type: ignore
                        reproduction_decorator(result.choices),
                        result.expected_traceback,  # type: ignore
                    ],
                )
                return True

        # If we haven't just discovered new branches and our example is larger than the
        # current largest minimal example, we can skip the expensive calculation.
        if (not branches.issubset(self.branch_counts)) or (
            self.results
            and sort_key(result.nodes)
            < sort_key(self.results.keys()[-1])  # type: ignore
            and any(
                sort_key(nodes) < sort_key(known_nodes)
                for branch, known_nodes in self.covering_nodes.items()
                if branch in branches
            )
        ):
            # We do this the stupid-but-obviously-correct way: add the new choices to
            # our tracked corpus, and then run a distillation step.
            self.results[result.nodes] = result
            as_bytes = choices_to_bytes(result.choices)
            self._database.save(self._fuzz_key, choices_to_bytes(result.choices))
            if observation is not None:
                assert isinstance(observation, dict)
                obs_key = cov_obs_key(self._fuzz_key, as_bytes)
                encoded = json.dumps(observation).encode()
                self._database.save(obs_key, encoded)
                for value in self._database.fetch(obs_key):
                    if value != encoded:
                        self._database.delete(obs_key, value)

            self._loaded_from_database.add(Choices(result.choices))
            # Clear out any redundant entries
            seen_branches: set[Branch] = set()
            self.covering_nodes = {}
            for res in list(self.results.values()):
                assert res.extra_information is not None
                covers = res.extra_information.branches - seen_branches  # type: ignore
                seen_branches.update(res.extra_information.branches)  # type: ignore
                if not covers:
                    del self.results[res.nodes]
                    as_bytes = choices_to_bytes(res.choices)
                    self._database.delete(self._fuzz_key, as_bytes)
                    # also clear out any observations
                    obs_key = cov_obs_key(self._fuzz_key, as_bytes)
                    for value in list(self._database.fetch(obs_key)):
                        self._database.delete(obs_key, value)
                else:
                    for branch in covers:
                        self.covering_nodes[branch] = res.nodes
            # We add newly-discovered branches to the counter later; so here our only
            # unseen branches should be the newly discovered branches.
            assert seen_branches - set(self.branch_counts) == branches - set(
                self.branch_counts
            )
            self.json_report = [
                [
                    reproduction_decorator(res.choices),
                    getattr(res.extra_information, "string_repr", "<unknown>"),
                    res.extra_information.reports,  # type: ignore
                ]
                for res in self.results.values()
            ]

        # Either update the branch counts so we can prioritize rarer branches in future,
        # or save an example with new coverage and reset the counter because we'll
        # have a different distribution with a new seed pool.
        if branches.issubset(self.branch_counts):
            self.branch_counts.update(branches)
        else:
            # Reset our seen branch counts.  This is essential because changing our
            # seed pool alters the probability of seeing each branch in future.
            # For details see AFL-fast, esp. the markov-chain trick.
            self.branch_counts = Counter(branches.union(self.branch_counts))

            # Save this choices as our minimal-known covering example for each new branch.
            if result.nodes not in self.results:
                self.results[result.nodes] = result
            self._database.save(self._fuzz_key, choices_to_bytes(result.choices))
            for branch in branches - set(self.covering_nodes):
                self.covering_nodes[branch] = nodes

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
           to shrink a choice sequence for branch A if it's already minimal for branch B.
           (because we'd have updated the best known for A while shrinking for B)
        2. All of the loops are designed to make some amount of progress, and then
           try again if they did not reach a fixpoint.  Almost all of the structures
           we're using can be mutated in the process, so it can get strange.
        """
        self._check_invariants()
        minimal_branches = {
            branch
            for branch, nodes in self.covering_nodes.items()
            if nodes in self.__shrunk_to_nodes
        }
        while set(self.covering_nodes) - minimal_branches:
            # The "largest first" shrinking order is designed to maximise the rate
            # of incidental progress, where shrinking hard problems stumbles over
            # smaller starting points for the easy ones.
            branch_to_shrink = max(
                set(self.covering_nodes) - minimal_branches,
                key=lambda b: sort_key(self.covering_nodes[b]),
            )
            shrinker = get_shrinker(
                self,
                fn,
                initial=self.results[self.covering_nodes[branch_to_shrink]],
                predicate=lambda d, b=branch_to_shrink: b
                in d.extra_information.branches,
                random=random,
            )
            shrinker.shrink()
            self.__shrunk_to_nodes.add(shrinker.shrink_target.nodes)
            minimal_branches |= {
                branch
                for branch, choices in self.covering_nodes.items()
                if choices == shrinker.shrink_target.choices
            }
            self._check_invariants()


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
            1 / min(self.pool.branch_counts[branch] for branch in res.extra_information.branches)  # type: ignore
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
