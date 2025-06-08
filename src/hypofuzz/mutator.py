import abc
from random import Random

from hypofuzz.corpus import Corpus, Fingerprint
from hypofuzz.database import ChoicesT


class Mutator(abc.ABC):
    def __init__(self, corpus: Corpus, random: Random) -> None:
        self.corpus = corpus
        self.random = random

    @abc.abstractmethod
    def generate_choices(self) -> ChoicesT:
        """
        Generate a choice sequence, usually by choosing and mutating examples from
        the corpus.
        """
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
        # (1 / rarest_behavior_count) for each choice sequence
        #
        # This is related to the AFL-fast trick, but doesn't track the transition
        # probabilities - just node densities in the markov chain.
        def _weight(fingerprint: Fingerprint) -> float:
            return 1 / min(
                self.corpus.behavior_counts[behavior] for behavior in fingerprint
            )

        weights = [
            # it's possible for a fingerprint to be empty. If it is, we expect
            # that to be the *only* fingerprint in the corpus, so it doesn't
            # matter what weight we assign to it (but we can't error by giving
            # an empty iterable to `min`, or dividing by zero with `total`.)
            (_weight(fingerprint) if fingerprint else 1)
            for fingerprint in self.corpus.fingerprints.keys()
        ]
        total = sum(weights)
        return [x / total for x in weights]

    def generate_choices(self) -> ChoicesT:
        """Splice together two known valid choice sequences.

        This is a pretty poor mutator, and not structure-aware, but works better than
        the blackbox one already.
        """
        if not self.corpus.fingerprints:
            return ()
        # Choose two previously-seen choice sequences to form a prefix and postfix,
        # plus some random bytes in the middle to pad it out a bit.
        # TODO: exploit the .examples tracking for structured mutation.
        nodes = self.random.choices(
            list(self.corpus.fingerprints.values()), weights=self._get_weights(), k=2
        )
        prefix = tuple(n.value for n in nodes[0])
        suffix = tuple(n.value for n in nodes[1])
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
