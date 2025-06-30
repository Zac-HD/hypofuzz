"""Adaptive fuzzing for property-based tests using Hypothesis."""

from collections import Counter, defaultdict
from collections.abc import Callable, Iterator, Set
from random import Random
from typing import TYPE_CHECKING, Union

from hypothesis import settings
from hypothesis.internal.conjecture.choice import (
    ChoiceNode,
    ChoiceT,
    choices_key,
)
from hypothesis.internal.conjecture.data import (
    ConjectureData,
    ConjectureResult,
    Status,
)
from hypothesis.internal.conjecture.engine import ConjectureRunner
from hypothesis.internal.conjecture.shrinker import Shrinker, sort_key as _sort_key
from hypothesis.internal.escalation import InterestingOrigin
from hypothesis.internal.observability import TestCaseObservation

from hypofuzz.database import ChoicesT, FailureState, HypofuzzDatabase, Observation

if TYPE_CHECKING:
    from typing import TypeAlias

NodesT: "TypeAlias" = tuple[ChoiceNode, ...]
# (start, end) where start = end = (filename, line, column)
Branch: "TypeAlias" = tuple[tuple[str, int, int], tuple[str, int, int]]
# Branch | event | target (use NewType for the latter two? they're both strings)
Behavior: "TypeAlias" = Union[Branch, str]
Fingerprint: "TypeAlias" = Set[Behavior]


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


def sort_key(nodes: Union[NodesT, ConjectureResult]) -> tuple[int, tuple[int, ...]]:
    """Sort choice nodes in shortlex order.

    See `hypothesis.internal.conjecture.engine.sort_key` for details on why we
    use shortlex order in particular.  This tweaked version is identical except
    for handling ConjectureResult objects too.
    """
    if isinstance(nodes, ConjectureResult):
        nodes = nodes.nodes
    return _sort_key(nodes)


def get_shrinker(
    fn: Callable[[ConjectureData], None],
    *,
    initial: Union[ConjectureData, ConjectureResult],
    predicate: Callable[..., bool],
    random: Random,
    explain: bool = False,
) -> Shrinker:
    return Shrinker(
        # don't pass our database to the shrinker; we'll manage writing failures
        # to the database ourselves, outside of the shrinker context.
        ConjectureRunner(
            fn,
            random=random,
            settings=settings(deadline=None),
        ),
        initial=initial,
        predicate=predicate,
        allow_transition=None,
        explain=explain,
    )


class Corpus:
    """Manage the corpus for a fuzz target.

    The corpus is responsible for managing all seed state, including saving
    novel seeds to the database.  This includes tracking how often each branch
    has been hit, minimal covering examples for each branch, and so on.
    """

    def __init__(self, database: HypofuzzDatabase, database_key: bytes) -> None:
        # The database and our database key is the stable identifiers for a corpus.
        # Everything else is reconstructed each run, and tracked only in memory.
        self.database_key = database_key
        self._db = database

        self.corpus: set[Choices] = set()
        # For each fingerprint, what's the minimal covering choice sequence?
        self.fingerprints: dict[Fingerprint, NodesT] = {}
        # How many times have we seen each branch since discovering our latest branch?
        self.behavior_counts: Counter[Behavior] = Counter()
        # if we have < 100% stability, one choice sequence might correspond
        # to multiple fingerprints. _count_fingerprints maps choice sequences to
        # the number of distinct fingerprints for that choice sequence.
        #
        # We only evict a choice sequence once it has zero remaining corresponding
        # fingerprints. The correctness of this refcounting is validated in
        # _check_invariants.
        self._count_fingerprints: dict[Choices, int] = defaultdict(int)
        self.interesting_examples: dict[InterestingOrigin, TestCaseObservation] = {}

        self.__shrunk_to_nodes: set[NodesT] = set()

    def __repr__(self) -> str:
        return (
            f"<Corpus\n    behavior_counts={self.behavior_counts}\n    "
            f"fingerprints={self.fingerprints}\n>"
        )

    def _check_invariants(self) -> None:
        assert set().union(*self.fingerprints) == set(self.behavior_counts)

        # under 100% stability, we expect these lengths to be equal. However, we
        # might execute choices A once with fingerprint F1 and again with a
        # different fingerprint F2, in which case we have one corpus element and
        # two fingerprints.
        assert len(self.corpus) <= len(self.fingerprints), (
            len(self.corpus),
            len(self.fingerprints),
            self.database_key,
        )

        for fingerprint, nodes in self.fingerprints.items():
            choices = Choices(tuple(n.value for n in nodes))
            assert choices in self.corpus, (fingerprint, choices)

        fingerprints_choices = [
            Choices(tuple(n.value for n in nodes))
            for nodes in self.fingerprints.values()
        ]
        for choices, count in self._count_fingerprints.items():
            assert count > 0  # we drop choices from _count_fingerprints once evicted
            assert fingerprints_choices.count(choices) == count

        assert self.corpus.issubset(
            set(fingerprints_choices)
        ), self.corpus.symmetric_difference(fingerprints_choices)

    def _add_fingerprint(
        self,
        fingerprint: Fingerprint,
        observation: TestCaseObservation,
        *,
        save_observation: bool,
    ) -> None:
        assert observation.metadata.choice_nodes is not None
        self.fingerprints[fingerprint] = observation.metadata.choice_nodes
        choices = Choices(tuple(n.value for n in observation.metadata.choice_nodes))
        if choices not in self.corpus:
            self._db.save_corpus(self.database_key, choices)
            if save_observation:
                self._db.save_corpus_observation(
                    self.database_key, choices, Observation.from_hypothesis(observation)
                )
        self.corpus.add(choices)
        self._count_fingerprints[choices] += 1

        # Reset our seen branch counts.  This is essential because changing our
        # corpus alters the probability of seeing each branch in future.
        # For details see AFL-fast, esp. the markov-chain trick.
        self.behavior_counts = Counter(fingerprint | set(self.behavior_counts))

    def _evict_choices(self, choices: Choices) -> None:
        # remove an outdated choice sequence and its observation(s) from the
        # database
        assert self._count_fingerprints[choices] == 0
        del self._count_fingerprints[choices]
        self.corpus.remove(choices)
        self._db.delete_corpus(self.database_key, choices)
        for observation in list(
            self._db.fetch_corpus_observations(self.database_key, choices)
        ):
            self._db.delete_corpus_observation(self.database_key, choices, observation)

    def would_change_coverage(
        self, fingerprint: Fingerprint, *, observation: TestCaseObservation
    ) -> bool:
        if observation.metadata.data_status < Status.VALID:
            return False

        assert observation.metadata.choice_nodes is not None

        # we don't need to check for new behaviors, since a new behavior implies
        # a new fingerprint.
        return fingerprint not in self.fingerprints or sort_key(
            observation.metadata.choice_nodes
        ) < sort_key(self.fingerprints[fingerprint])

    def would_change_failure(self, observation: TestCaseObservation) -> bool:
        if observation.metadata.data_status is not Status.INTERESTING:
            return False

        origin = observation.metadata.interesting_origin
        assert origin is not None
        assert observation.metadata.choice_nodes is not None

        new_failure = origin not in self.interesting_examples
        smaller_choices = origin in self.interesting_examples and sort_key(
            observation.metadata.choice_nodes
        ) < sort_key(
            self.interesting_examples[origin].metadata.choice_nodes  # type: ignore
        )
        return new_failure or smaller_choices

    def consider_coverage(
        self,
        behaviors: Set[Behavior],
        *,
        observation: TestCaseObservation,
        save_observation: bool,
    ) -> None:
        if observation.metadata.data_status < Status.VALID:
            return

        assert observation.metadata.choice_nodes is not None

        self.behavior_counts.update(behaviors)
        if behaviors not in self.fingerprints:
            self._add_fingerprint(
                behaviors, observation, save_observation=save_observation
            )

        if sort_key(observation.metadata.choice_nodes) < sort_key(
            self.fingerprints[behaviors]
        ):
            existing_choices = Choices(
                tuple(n.value for n in self.fingerprints[behaviors])
            )

            self._count_fingerprints[existing_choices] -= 1
            self._add_fingerprint(
                behaviors, observation, save_observation=save_observation
            )
            if self._count_fingerprints[existing_choices] == 0:
                self._evict_choices(existing_choices)

    def consider_failure(
        self,
        observation: TestCaseObservation,
    ) -> None:
        if not self.would_change_failure(observation):
            return

        origin = observation.metadata.interesting_origin
        assert observation.metadata.choice_nodes is not None
        assert origin is not None

        previous = self.interesting_examples.get(origin)
        choices = tuple(n.value for n in observation.metadata.choice_nodes)
        self.interesting_examples[origin] = observation
        # We save interesting examples to the unshrunk/secondary database
        # so they can appear immediately without waiting for shrinking to
        # finish. (also in case of a fatal hypofuzz error etc).
        self._db.save_failure(
            self.database_key,
            choices,
            Observation.from_hypothesis(observation),
            state=FailureState.UNSHRUNK,
        )

        if previous is not None:
            assert previous.metadata.choice_nodes is not None
            previous_choices = tuple(n.value for n in previous.metadata.choice_nodes)
            # remove the now-redundant failure we had previously saved.
            self._db.delete_failure(
                self.database_key,
                previous_choices,
                state=FailureState.UNSHRUNK,
            )

    def distill(self, fn: Callable[[ConjectureData], None], random: Random) -> None:
        """Shrink to a corpus of *minimal* covering examples.

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
        minimal_behaviors = {
            branch
            for branch, nodes in self.fingerprints.items()
            if nodes in self.__shrunk_to_nodes
        }
        while set(self.fingerprints) - minimal_behaviors:
            # The "largest first" shrinking order is designed to maximise the rate
            # of incidental progress, where shrinking hard problems stumbles over
            # smaller starting points for the easy ones.
            branch_to_shrink = max(
                set(self.fingerprints) - minimal_behaviors,
                key=lambda b: sort_key(self.fingerprints[b]),
            )
            shrinker = get_shrinker(
                fn,
                initial=ConjectureData.for_choices(
                    [node.value for node in self.fingerprints[branch_to_shrink]]
                ),
                predicate=lambda d, b=branch_to_shrink: (
                    b in d.extra_information.behaviors
                ),
                random=random,
            )
            shrinker.shrink()
            self.__shrunk_to_nodes.add(shrinker.shrink_target.nodes)
            minimal_behaviors |= {
                branch
                for branch, choices in self.fingerprints.items()
                if choices == shrinker.shrink_target.choices
            }
