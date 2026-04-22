"""Solver-bridge strategy for HypoFuzz.

When HypoFuzz's greybox engine gets stuck -- small mutations can't discover
any more branches -- spending some wall clock on symbolic execution via
``hypothesis-crosshair`` can unblock it. This module exposes the solver
as a *strategy* peer to the existing greybox generation/mutation loop.
Scheduling is unified: both strategies advertise an estimated
"behaviors per second", and :func:`choose_strategy` picks whichever
currently looks more productive (Boltzmann / softmax weighting over the
estimators, matching the per-target scheduler in :mod:`hypofuzz.bayes`).

Tracking issue: https://github.com/pschanely/hypothesis-crosshair/issues/26

The bridge is intentionally non-intrusive: importing this module does not
modify the fuzzer. Integration is by composition -- construct a
``SolverBridge(target)``, consult :func:`choose_strategy` at each
scheduling point, and call ``bridge.run_solver_phase()`` when it picks
``"solver"``.

Key data flow
-------------

- CrossHair discovers new concrete choice sequences; we capture each
  via Hypothesis's observability callback and write it to the HypoFuzz
  corpus DB key.
- The greybox worker's existing DB listener re-enqueues those sequences
  for replay under ``HypofuzzProvider``, where coverage is measured and
  acceptance is decided exactly as for any other discovered seed. No
  separate coverage accounting is introduced.
- Warm-starting CrossHair from corpus seeds via
  ``PrimitiveProvider.replay_choices()`` is wired up but disabled by
  default: CrossHair's SMT query time can blow up when a hint can't
  satisfy the downstream path conditions.
"""

from __future__ import annotations

import random as _random_module
import time
from collections import deque
from dataclasses import dataclass, field
from random import Random
from typing import Any, Literal

import hypothesis.internal.observability as observability
from hypothesis.errors import BackendCannotProceed, StopTest
from hypothesis.internal.conjecture.data import ConjectureData
from hypothesis.internal.observability import with_observability_callback

from hypofuzz.bayes import behaviors_per_second, softmax


def _is_available() -> bool:
    try:
        import hypothesis_crosshair_provider.crosshair_provider  # noqa: F401
    except Exception:
        return False
    return True


@dataclass
class SolverBridge:
    """Run CrossHair as a peer strategy to HypoFuzz's greybox generation.

    ``target`` must be a :class:`hypofuzz.hypofuzz.FuzzTarget` whose fixtures
    have already been entered. One ``SolverBridge`` manages one target.
    """

    target: Any  # FuzzTarget; untyped to avoid an import cycle.

    # Per-phase wall-clock budget. Phases end promptly at this time, which
    # makes the estimated-rate signal stable and caps the cost of one bad
    # invocation.
    phase_budget_seconds: float = 10.0
    # How many warm-start seeds to hand CrossHair via ``replay_choices()``.
    # See module docstring -- default 0.
    warm_start_count: int = 0
    # Prior estimate for behaviors/sec before the first phase has run. The
    # scheduler treats this as the solver's rate until we have real data.
    # Deliberately optimistic: greybox already has a self-estimate from its
    # own history, so the solver only gets sampled if the prior is
    # competitive with it -- otherwise the warm-up cost is wasted.
    rate_prior: float = 0.5

    _random: Random = field(default_factory=Random)
    # Rolling history of (new_fingerprints, phase_seconds) pairs. Used to
    # estimate behaviors/sec; bounded to keep the signal recent.
    _history: deque[tuple[int, float]] = field(default_factory=lambda: deque(maxlen=8))

    def is_available(self) -> bool:
        return _is_available()

    # --- strategy interface ------------------------------------------------

    def estimated_behaviors_per_second(self) -> float:
        """Current estimate of new fingerprints per wall-clock second, as
        attributable to the solver. Returns :attr:`rate_prior` until the
        first phase has observed its own delta."""
        if not self._history:
            return self.rate_prior
        total_fp = sum(n for n, _ in self._history)
        total_s = sum(s for _, s in self._history)
        if total_s <= 0:
            return self.rate_prior
        return total_fp / total_s

    def run_solver_phase(self) -> None:
        """Run one solver phase against the target's Hypothesis state,
        writing unique realised choice sequences to the corpus DB key. The
        greybox worker's DB listener picks those up automatically."""
        if not self.is_available():
            return

        from hypothesis_crosshair_provider.crosshair_provider import (
            CrossHairPrimitiveProvider,
        )
        from hypofuzz.corpus import Choices

        target = self.target
        provider = target.provider
        assert target.state is not None
        assert provider.corpus is not None

        fp_before = len(provider.corpus.fingerprints)
        phase_start = time.perf_counter()

        cross = CrossHairPrimitiveProvider()
        for seed in self._select_warm_start_seeds():
            cross.replay_choices(seed)

        # choice_nodes is only populated in observations when this is on.
        prev_obs_choices = observability.OBSERVABILITY_CHOICES
        observability.OBSERVABILITY_CHOICES = True

        captured: list[tuple] = []
        dedupe: set[tuple] = set()

        def capture(obs_):
            # Realise each observation's choice_nodes while we are still
            # inside CrossHair's per-test-case statespace; after the
            # context manager exits, ``cross.realize()`` can no longer
            # reconstruct concrete values.
            if obs_.type != "test_case":
                return
            if obs_.metadata.choice_nodes is None:
                return
            try:
                realized = tuple(
                    cross.realize(n.value) for n in obs_.metadata.choice_nodes
                )
            except BackendCannotProceed:
                return
            except Exception:
                # CrossHair realize() occasionally fails on some targets;
                # we silently skip those observations.
                return
            if realized in dedupe:
                return
            dedupe.add(realized)
            captured.append(realized)

        corpus_choices = provider.corpus.corpus

        try:
            with with_observability_callback(capture):
                deadline = phase_start + self.phase_budget_seconds
                while time.perf_counter() < deadline:
                    data = ConjectureData(provider=cross, random=self._random)
                    try:
                        target.state._execute_once_for_engine(data)
                    except (StopTest, BackendCannotProceed):
                        pass
                    except BaseException:
                        break
        finally:
            observability.OBSERVABILITY_CHOICES = prev_obs_choices

        for realized in captured:
            if Choices(realized) not in corpus_choices:
                target.database.corpus.save(target.database_key, realized)

        phase_seconds = max(time.perf_counter() - phase_start, 1e-6)
        fp_after = len(provider.corpus.fingerprints)
        self._history.append((fp_after - fp_before, phase_seconds))

    # --- helpers ---------------------------------------------------------

    def _select_warm_start_seeds(self) -> list[tuple]:
        if self.warm_start_count <= 0:
            return []
        corpus = self.target.provider.corpus
        if not corpus or not corpus.fingerprints:
            return []

        def rarity(nodes) -> float:
            # the fingerprint whose nodes is identically this one
            fp = next(
                (fp for fp, n in corpus.fingerprints.items() if n is nodes), None
            )
            if fp is None:
                return float("inf")
            return min(
                (corpus.behavior_counts.get(b, 1) for b in fp), default=float("inf")
            )

        ranked = sorted(corpus.fingerprints.items(), key=lambda kv: rarity(kv[1]))
        seen: set[tuple] = set()
        seeds: list[tuple] = []
        for _, nodes in ranked:
            if len(seeds) >= self.warm_start_count:
                break
            r = tuple(n.value for n in nodes)
            if r in seen:
                continue
            seen.add(r)
            seeds.append(r)
        return seeds


# ---------------------------------------------------------------------------
# unified scheduler: generation/mutation/solver all compete on the same signal
# ---------------------------------------------------------------------------


Strategy = Literal["greybox", "solver"]


def choose_strategy(
    target: Any,
    bridge: SolverBridge | None,
    *,
    random: Random | None = None,
) -> Strategy:
    """Pick the next strategy by softmaxing over per-strategy estimates of
    behaviors per second.

    This mirrors the per-target selection in :mod:`hypofuzz.bayes`:
    ``behaviors_per_second`` is the common signal, and the choice is
    Boltzmann-weighted over the available arms. Greybox and solver are
    the arms here; the same pattern extends cleanly to generation vs.
    mutation within greybox.
    """
    if bridge is None or not bridge.is_available():
        return "greybox"
    rates = [behaviors_per_second(target), bridge.estimated_behaviors_per_second()]
    weights = softmax(rates)
    rng = random if random is not None else _random_module
    return rng.choices(("greybox", "solver"), weights=weights, k=1)[0]
