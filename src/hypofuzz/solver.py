"""Solver-bridge phase for HypoFuzz.

When the coverage-guided greybox engine stalls (no new behavior for a while),
invoke a short burst of symbolic-execution-driven exploration via
``hypothesis-crosshair`` / CrossHair. The solver-discovered choice sequences
are written back into HypoFuzz's corpus database where the normal DB listener
replays them under ``HypofuzzProvider``, so coverage bookkeeping stays in one
place.

Motivation: mixing coverage-guided and solver-based approaches is qualitatively
stronger than either alone. Greybox mutation is great at small, frequent
neighborhood moves but struggles with deep nested predicates on large input
spaces; a solver cracks those trivially. See
https://github.com/pschanely/hypothesis-crosshair/issues/26.

Concrete mechanism

    1. Detect a stall via ``HypofuzzProvider.since_new_behavior``.
    2. Optionally pick a few covering choice sequences from the corpus and
       hand them to CrossHair via ``PrimitiveProvider.replay_choices()`` --
       CrossHair's symbolic run is then biased to follow that concrete
       input for the next iteration, and subsequent iterations explore
       still-unvisited siblings in the path tree. Warm-start is off by
       default: CrossHair's native tree search already spreads out quickly,
       and a warm-start seed that happens to miss the deep path can make
       its SMT query take tens of seconds.
    3. Run a bounded wall-clock budget of CrossHair iterations against the
       target's existing Hypothesis ``state``, swapping in a
       ``CrossHairPrimitiveProvider`` via ``ConjectureData(provider=...)``.
       Each iteration's realised choice sequence is captured from the
       Hypothesis observation stream and deduplicated.
    4. Save the unique realised sequences to the HypoFuzz corpus DB key.
       The greybox worker's DB listener picks them up automatically and
       enqueues them for replay under ``HypofuzzProvider``, at which point
       coverage is measured and acceptance is decided exactly as for any
       other discovered seed.

The bridge is intentionally non-intrusive: importing ``solver`` does not
modify the fuzzer. Wire it in by constructing a ``SolverBridge(target)`` and
calling ``maybe_run()`` between greybox iterations (see
``scripts/solver_demo.py`` for a self-contained driver).
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from random import Random
from typing import Any

import hypothesis.internal.observability as observability
from hypothesis.errors import BackendCannotProceed, StopTest
from hypothesis.internal.conjecture.data import ConjectureData
from hypothesis.internal.observability import with_observability_callback


@dataclass
class SolverStats:
    """Counters for how useful the solver phase has been."""

    invocations: int = 0
    iters_run: int = 0
    seeds_proposed: int = 0
    unique_seeds_proposed: int = 0
    time_in_solver: float = 0.0
    errors: int = 0
    last_invocation_new_corpus: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "invocations": self.invocations,
            "iters_run": self.iters_run,
            "seeds_proposed": self.seeds_proposed,
            "unique_seeds_proposed": self.unique_seeds_proposed,
            "time_in_solver": round(self.time_in_solver, 3),
            "errors": self.errors,
        }


@dataclass
class SolverBridge:
    """Invokes CrossHair to propose novel seeds when the greybox engine stalls.

    ``target`` must be a ``hypofuzz.hypofuzz.FuzzTarget`` (or any object with
    the same ``provider``, ``state``, ``database``, ``database_key``
    attributes) whose fixtures have already been entered.
    """

    target: Any  # FuzzTarget; not typed to avoid an import cycle at import time

    # How many successive mutation-phase inputs without a new behavior qualify
    # as "stalled" and trigger a solver phase.
    stall_threshold: int = 500
    # Don't invoke the solver more often than this many wall-clock seconds
    # (measured from the end of the last phase).
    min_reinvoke_interval: float = 30.0
    # Wall-clock budget spent in a single solver phase.
    solver_budget_seconds: float = 20.0
    # How many warm-start seeds to hand CrossHair per invocation.
    #
    # CrossHair iterations that are warm-started with a seed which doesn't
    # happen to satisfy the downstream path conditions can take much longer
    # than the native SMT-driven tree search: the solver has to prove the
    # hint's path is infeasible, which for deep equality/magic-value tests
    # can be tens of seconds per iteration. Default to 0 and rely on
    # CrossHair's own tree search; set a positive value for targets where
    # warm-starting demonstrably helps (experimental).
    warm_start_count: int = 0
    # Emit per-phase diagnostic prints.
    debug: bool = False

    stats: SolverStats = field(default_factory=SolverStats)
    _last_invoked_at: float = -1e9
    _disabled_reason: str | None = None
    _random: Random = field(default_factory=Random)

    # --- availability + scheduling ----------------------------------------

    def is_available(self) -> bool:
        """Return True iff ``hypothesis-crosshair`` / ``crosshair-tool`` are
        importable."""
        if self._disabled_reason is not None:
            return False
        try:
            import hypothesis_crosshair_provider.crosshair_provider  # noqa: F401
        except Exception as exc:  # pragma: no cover - environment-dependent
            self._disabled_reason = f"hypothesis-crosshair not importable: {exc!r}"
            return False
        return True

    def should_invoke(self) -> bool:
        """Return True if the greybox engine looks stalled and the solver
        hasn't run in the recent past."""
        if not self.is_available():
            return False
        provider = getattr(self.target, "provider", None)
        if provider is None or getattr(provider, "corpus", None) is None:
            return False
        if provider.since_new_behavior < self.stall_threshold:
            return False
        now = time.perf_counter()
        if now - self._last_invoked_at < self.min_reinvoke_interval:
            return False
        return True

    def maybe_run(self) -> bool:
        """Run a solver phase if the engine is stalled. Return True iff one
        ran."""
        if not self.should_invoke():
            return False
        self.run_solver_phase()
        return True

    # --- the phase -------------------------------------------------------

    def _select_warm_start_seeds(self) -> list[tuple]:
        """Pick up to ``warm_start_count`` covering choice sequences from the
        current corpus, favouring those that contribute to rare branches (the
        AFL-fast signal already computed in ``corpus.behavior_counts``)."""
        if self.warm_start_count <= 0:
            return []

        corpus = self.target.provider.corpus
        assert corpus is not None
        if not corpus.fingerprints:
            return []

        behavior_counts = corpus.behavior_counts

        def rarity_score(nodes) -> float:
            # Lower score = the fingerprint contains a rare branch.
            fp = next(
                (fp for fp, n in corpus.fingerprints.items() if n is nodes), None
            )
            if fp is None:
                return float("inf")
            return min(
                (behavior_counts.get(b, 1) for b in fp),
                default=float("inf"),
            )

        ranked = sorted(
            corpus.fingerprints.items(), key=lambda kv: rarity_score(kv[1])
        )
        seen: set[tuple] = set()
        seeds: list[tuple] = []
        for _, nodes in ranked:
            if len(seeds) >= self.warm_start_count:
                break
            realized = tuple(n.value for n in nodes)
            if realized in seen:
                continue
            seen.add(realized)
            seeds.append(realized)
        return seeds

    def _log(self, msg: str) -> None:
        if self.debug:
            print(f"[solver-bridge] {msg}", flush=True)

    def run_solver_phase(self) -> None:
        """Run one solver phase. Writes realised choice sequences to the
        HypoFuzz corpus DB key; the DB listener re-enqueues them for replay
        under ``HypofuzzProvider``."""
        # Imported lazily to keep hypothesis-crosshair strictly optional.
        from hypothesis_crosshair_provider.crosshair_provider import (
            CrossHairPrimitiveProvider,
        )

        target = self.target
        provider = target.provider
        assert target.state is not None, (
            "SolverBridge.run_solver_phase called before the target's "
            "Hypothesis state was initialized (did you forget to call "
            "target._enter_fixtures?)"
        )

        self.stats.invocations += 1
        self._last_invoked_at = time.perf_counter()
        phase_start = self._last_invoked_at

        warm_seeds = self._select_warm_start_seeds()
        self._log(
            f"begin phase #{self.stats.invocations} "
            f"warm_seeds={len(warm_seeds)} budget={self.solver_budget_seconds}s"
        )

        cross = CrossHairPrimitiveProvider()
        for seed in warm_seeds:
            cross.replay_choices(seed)

        # choice_nodes is only populated in observations when this flag is on.
        prev_obs_choices = observability.OBSERVABILITY_CHOICES
        observability.OBSERVABILITY_CHOICES = True

        # Realise each captured observation's choice_nodes INSIDE the
        # callback. The callback fires while we're still in CrossHair's
        # per-test-case state-space, which is what ``realize()`` needs to
        # reconstruct concrete values.
        captured: list[tuple] = []
        dedupe: set[tuple] = set()

        def capture(obs_):
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
                # realization occasionally fails deep inside CrossHair on
                # some targets; we silently skip those observations.
                return
            if realized in dedupe:
                return
            dedupe.add(realized)
            captured.append(realized)

        corpus_choices = (
            self.target.provider.corpus.corpus if provider.corpus else set()
        )

        iters = 0
        last_beat = time.perf_counter()
        try:
            with with_observability_callback(capture):
                deadline = phase_start + self.solver_budget_seconds
                while time.perf_counter() < deadline:
                    iters += 1
                    if self.debug and time.perf_counter() - last_beat > 2.0:
                        self._log(
                            f"  iter={iters} captured={len(captured)} "
                            f"elapsed={time.perf_counter()-phase_start:.1f}s"
                        )
                        last_beat = time.perf_counter()
                    data = ConjectureData(provider=cross, random=self._random)
                    try:
                        target.state._execute_once_for_engine(data)
                    except StopTest:
                        pass
                    except BackendCannotProceed:
                        pass
                    except BaseException:
                        self.stats.errors += 1
                        # abort the phase on unexpected internal error
                        break
        finally:
            observability.OBSERVABILITY_CHOICES = prev_obs_choices

        # Save each unique realised sequence to the corpus DB key; the
        # greybox worker's DB listener replays and evaluates them under
        # HypofuzzProvider (where coverage-novelty is decided).
        from hypofuzz.corpus import Choices
        unique_seeds_proposed = len(captured)
        seeds_saved = 0
        for realized in captured:
            if Choices(realized) in corpus_choices:
                continue
            target.database.corpus.save(target.database_key, realized)
            seeds_saved += 1

        self.stats.iters_run += iters
        self.stats.seeds_proposed += seeds_saved
        self.stats.unique_seeds_proposed += unique_seeds_proposed
        self.stats.time_in_solver += time.perf_counter() - phase_start
        self.stats.last_invocation_new_corpus = seeds_saved
        self._log(
            f"end phase: iters={iters} unique={unique_seeds_proposed} "
            f"saved={seeds_saved} "
            f"elapsed={time.perf_counter() - phase_start:.2f}s"
        )

    # --- utilities -------------------------------------------------------

    def force_run(self, seeds: Iterable[tuple] | None = None) -> None:
        """Test utility: force a solver phase regardless of stall state.
        If ``seeds`` is given, overrides warm-start selection for this call."""
        if seeds is None:
            self.run_solver_phase()
            return
        original = self._select_warm_start_seeds

        def _override() -> list[tuple]:
            return list(seeds)

        self._select_warm_start_seeds = _override  # type: ignore[assignment]
        try:
            self.run_solver_phase()
        finally:
            self._select_warm_start_seeds = original  # type: ignore[assignment]
