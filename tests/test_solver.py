"""Tests for the HypoFuzz x CrossHair solver bridge.

The feature makes two claims, one per test:

1. ``test_solver_bridge_unblocks_deep_equality_branch`` -- running the
   solver phase discovers a nested equality predicate that plain greybox
   fuzzing cannot crack within any reasonable input budget, and the
   discovered seed is picked up by HypoFuzz's normal corpus machinery so
   the fuzzer's own fingerprint set grows as a result.

2. ``test_choose_strategy_follows_behaviors_per_second`` -- the
   within-target choice between greybox and solver uses the same
   estimator pattern as the per-target scheduler in :mod:`hypofuzz.bayes`,
   so whichever arm has a higher estimated rate of new behaviors is
   preferred.
"""

from random import Random

import pytest
from hypothesis import given, strategies as st
from hypothesis.database import InMemoryExampleDatabase, ListenerEventT

pytest.importorskip("hypothesis_crosshair_provider.crosshair_provider")

from hypofuzz.database import DatabaseEvent, HypofuzzDatabase  # noqa: E402
from hypofuzz.hypofuzz import FuzzTarget  # noqa: E402
from hypofuzz.solver import SolverBridge, choose_strategy  # noqa: E402


def _fuzz_target_for(test_fn):
    """Wire up a FuzzTarget against an in-memory DB, with the same DB
    listener FuzzWorker installs so corpus-save events get picked up."""
    db_raw = InMemoryExampleDatabase()
    target = FuzzTarget.from_hypothesis_test(test_fn, database=HypofuzzDatabase(db_raw))
    target._enter_fixtures()

    def forward(event: ListenerEventT) -> None:
        ev = DatabaseEvent.from_event(event)
        if ev is not None and ev.database_key == target.database_key:
            target.provider.on_event(ev)

    db_raw.add_listener(forward)
    return target


def _fingerprint_count(target) -> int:
    return len(target.provider.corpus.fingerprints)


def test_solver_bridge_unblocks_deep_equality_branch():
    # The deep branch requires x+y==13 AND x*y==42 over integers in
    # [-1e9, 1e9]^2 -- the solution set is the two points {(6,7), (7,6)},
    # a probability of 2 / (2e9)**2 for blackbox mutation.  Mid-depth
    # branches on x+y==13 and x*y==42 individually are also far outside
    # blackbox reach for any small budget.
    @given(st.integers(-10**9, 10**9), st.integers(-10**9, 10**9))
    def test(x, y):
        if x + y == 13:
            pass
        if x * y == 42:
            pass
        if x > 0 and y > 0 and x + y == 13 and x * y == 42:
            pass

    target = _fuzz_target_for(test)
    # Warm up the greybox engine enough that its own fingerprint set has
    # plateaued on the shallow branches. The deep equality branches stay
    # out of reach for greybox no matter how long we wait, because the
    # mutation neighborhood over 2^60 int pairs is vanishingly unlikely
    # to stumble onto an integer solution to a two-variable polynomial
    # system.
    for _ in range(3000):
        target.run_one()
    pre_solver_fps = _fingerprint_count(target)

    # One bounded solver phase is enough to crack the nested predicate.
    # The seeds it proposes are written to the HypoFuzz corpus DB; the
    # DB listener enqueues them; draining the queue is a pure greybox
    # activity, and the replay-under-HypofuzzProvider is where new
    # fingerprints officially register.
    SolverBridge(target, phase_budget_seconds=5.0).run_solver_phase()
    while target.provider._choices_queue:
        target.run_one()

    post_solver_fps = _fingerprint_count(target)
    assert post_solver_fps > pre_solver_fps, (
        f"solver phase contributed no new fingerprints "
        f"(before={pre_solver_fps}, after={post_solver_fps})"
    )


def test_choose_strategy_follows_behaviors_per_second(monkeypatch):
    # Build a minimal FuzzTarget; we don't actually fuzz, just probe the
    # scheduler's arithmetic.
    @given(st.integers())
    def test(x):
        pass

    target = _fuzz_target_for(test)
    bridge = SolverBridge(target)

    # Stub the two estimators so we can drive the scheduler deterministically.
    from hypofuzz import solver as solver_module

    monkeypatch.setattr(solver_module, "behaviors_per_second", lambda _t: 1.0)

    # Case A: solver's advertised rate is much lower; softmax should
    # overwhelmingly pick greybox.
    bridge.rate_prior = 0.01
    rng = Random(0)
    counts = {"greybox": 0, "solver": 0}
    for _ in range(400):
        counts[choose_strategy(target, bridge, random=rng)] += 1
    assert counts["greybox"] > counts["solver"] * 2

    # Case B: solver rate is much higher -- preference flips.
    bridge.rate_prior = 100.0
    rng = Random(0)
    counts = {"greybox": 0, "solver": 0}
    for _ in range(400):
        counts[choose_strategy(target, bridge, random=rng)] += 1
    assert counts["solver"] > counts["greybox"] * 2
