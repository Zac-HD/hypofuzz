#!/usr/bin/env python3
"""Demonstration harness for the HypoFuzz × CrossHair solver-bridge prototype.

Runs a user-supplied property test twice:

  * baseline    — vanilla HypoFuzz greybox fuzzing
  * augmented   — same, but with a SolverBridge that, whenever the fuzzer
                  stalls (no new behavior for N inputs in a row), spins up
                  CrossHair warm-started with covering corpus seeds.

Records coverage-over-time (number of distinct behaviors = branches + events)
for both runs, then prints a quantitative comparison + optional CSV output.

Usage:

    python scripts/solver_demo.py [--time-budget N] [--stall-threshold N]
                                  [--solver-budget N] [--target NAME]
                                  [--out-dir DIR]

The default target is ``deep_eq`` (two ints, must satisfy both x+y==13 and
x*y==42 to hit the deep branch). Other targets are registered in TARGETS below.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from hypothesis import given, settings as hyp_settings, strategies as st
from hypothesis.database import InMemoryExampleDatabase, ListenerEventT

from hypofuzz.database import DatabaseEvent, HypofuzzDatabase
from hypofuzz.hypofuzz import FuzzTarget
from hypofuzz.solver import SolverBridge


# ---------------------------------------------------------------------------
# Demo targets. Each is a `@given` test function; all just pass but contain
# hard-to-reach branches that exercise coverage tracking.
# ---------------------------------------------------------------------------

# Side-effect sink for deep-branch detection: {label -> first-hit wallclock}
DEEP_HITS: dict[str, float] = {}
DEEP_T0: float = 0.0


def _hit(label: str) -> None:
    if label not in DEEP_HITS:
        DEEP_HITS[label] = time.perf_counter() - DEEP_T0


def _make_deep_eq_target():
    @given(st.integers(-10**9, 10**9), st.integers(-10**9, 10**9))
    @hyp_settings(deadline=None, database=None, max_examples=1)
    def test(x, y):
        # shallow branches
        if x > 0:
            _hit("x>0")
        if y > 0:
            _hit("y>0")
        # mid branches
        if x + y == 13:
            _hit("x+y==13")
        if x * y == 42:
            _hit("x*y==42")
        # deep branch: blackbox mutation is extremely unlikely to find this
        # in the int-range [-1e9, 1e9]^2 space, but a solver cracks it
        # trivially.
        if x > 0 and y > 0 and x + y == 13 and x * y == 42:
            _hit("DEEP_1:x+y=13 AND x*y=42")
        # a SECOND deep branch with different magic constants, warm-starting
        # from the first will not help find this one.
        if x > 100 and y > 100 and x - y == 11 and x + y == 999:
            _hit("DEEP_2:x-y=11 AND x+y=999")

    return test


def _make_magic_ints_target():
    @given(st.lists(st.integers(-10**6, 10**6), min_size=3, max_size=3))
    @hyp_settings(deadline=None, database=None, max_examples=1)
    def test(xs):
        if len(xs) != 3:
            return
        a, b, c = xs
        if a == 0xBADF00D % (10**6):
            _hit("a==BADF00D")
        if a == 0xBADF00D % (10**6) and b == 0xC0FFEE % (10**6):
            _hit("a==BADF00D AND b==C0FFEE")
        if (
            a == 0xBADF00D % (10**6)
            and b == 0xC0FFEE % (10**6)
            and c == 0xDEADBEEF % (10**6)
        ):
            _hit("DEEP:a=BADF00D AND b=C0FFEE AND c=DEADBEEF")

    return test


def _make_sum_eq_target():
    @given(st.lists(st.integers(0, 2**30), min_size=5, max_size=5))
    @hyp_settings(deadline=None, database=None, max_examples=1)
    def test(xs):
        # Hit a branch iff the list sums to a specific ten-digit number.
        s = sum(xs)
        if s == 0x13370815:
            _hit("sum==13370815")
        if s == 0x13370815 and xs[0] == xs[-1]:
            _hit("DEEP:sum==13370815 AND xs[0]==xs[-1]")

    return test


def _make_string_tree_target():
    @given(st.text(min_size=0, max_size=16))
    @hyp_settings(deadline=None, database=None, max_examples=1)
    def test(s):
        # A magic-string gate.
        if len(s) >= 4 and s[0] == "M":
            _hit("s[0]=M")
        if len(s) >= 4 and s[0] == "M" and s[1] == "A":
            _hit("s[:2]=MA")
        if len(s) >= 4 and s[0] == "M" and s[1] == "A" and s[2] == "G":
            _hit("s[:3]=MAG")
        if (
            len(s) >= 4
            and s[0] == "M"
            and s[1] == "A"
            and s[2] == "G"
            and s[3] == "E"
        ):
            _hit("DEEP:s startswith MAGE")

    return test


TARGETS: dict[str, Callable] = {
    "deep_eq": _make_deep_eq_target,
    "magic_ints": _make_magic_ints_target,
    "sum_eq": _make_sum_eq_target,
    "string_tree": _make_string_tree_target,
}


# ---------------------------------------------------------------------------
# A/B harness
# ---------------------------------------------------------------------------


@dataclass
class CoverageSample:
    elapsed: float
    iters: int
    behaviors: int
    fingerprints: int
    since_new_behavior: int
    corpus_size: int
    solver_invocations: int = 0
    solver_seeds: int = 0

    def as_row(self) -> list:
        return [
            round(self.elapsed, 3),
            self.iters,
            self.behaviors,
            self.fingerprints,
            self.since_new_behavior,
            self.corpus_size,
            self.solver_invocations,
            self.solver_seeds,
        ]


@dataclass
class RunResult:
    mode: str
    samples: list[CoverageSample] = field(default_factory=list)
    final_behaviors: int = 0
    final_fingerprints: int = 0
    final_iters: int = 0
    final_elapsed: float = 0.0
    solver_stats: dict | None = None
    deep_branches_hit: dict[str, float] = field(default_factory=dict)

    def as_summary(self) -> dict:
        return {
            "mode": self.mode,
            "final_behaviors": self.final_behaviors,
            "final_fingerprints": self.final_fingerprints,
            "final_iters": self.final_iters,
            "final_elapsed": round(self.final_elapsed, 3),
            "solver_stats": self.solver_stats,
            "deep_branches_hit": {
                k: round(v, 3) for k, v in self.deep_branches_hit.items()
            },
        }




def run_campaign(
    target_name: str,
    *,
    time_budget: float,
    use_solver: bool,
    stall_threshold: int,
    solver_budget_seconds: float,
    min_reinvoke_interval: float,
    sample_interval: float = 0.25,
    seed: int = 0,
) -> RunResult:
    """Run a single HypoFuzz campaign on ``target_name`` for up to
    ``time_budget`` wall-clock seconds. If ``use_solver``, attach the
    SolverBridge and invoke it on stall. Returns a RunResult."""
    print(f"run_campaign: target={target_name} solver={use_solver} budget={time_budget}",
          flush=True)
    random.seed(seed)
    factory = TARGETS[target_name]
    test_fn = factory()

    # reset side-effect state for this run
    global DEEP_T0
    DEEP_HITS.clear()
    DEEP_T0 = time.perf_counter()

    db_raw = InMemoryExampleDatabase()
    db = HypofuzzDatabase(db_raw)
    target = FuzzTarget.from_hypothesis_test(test_fn, database=db)
    # fix the worker-side Random so solver vs baseline differ only in solver phase
    target.random = random.Random(seed)
    target._enter_fixtures()

    bridge: SolverBridge | None = None
    if use_solver:
        bridge = SolverBridge(
            target,
            stall_threshold=stall_threshold,
            solver_budget_seconds=solver_budget_seconds,
            min_reinvoke_interval=min_reinvoke_interval,
        )

    # Wire the DB listener so solver-written corpus entries get picked up by
    # the fuzz provider (same mechanism FuzzWorker uses).
    _listener_stats = {"events": 0, "forwarded": 0}

    def _on_event(listener_event: ListenerEventT) -> None:
        _listener_stats["events"] += 1
        event = DatabaseEvent.from_event(listener_event)
        if event is None or event.database_key != target.database_key:
            return
        _listener_stats["forwarded"] += 1
        target.provider.on_event(event)

    db_raw.add_listener(_on_event)

    result = RunResult(mode="solver" if use_solver else "baseline")

    start = time.perf_counter()
    last_sample = start
    last_dbg = start
    iters = 0
    while True:
        now = time.perf_counter()
        elapsed = now - start
        if elapsed >= time_budget:
            break

        target.run_one()
        iters += 1

        if now - last_dbg >= 5.0:
            corpus = target.provider.corpus
            print(
                f"  [t={elapsed:.1f}s] iters={iters} "
                f"behaviors={len(corpus.behavior_counts) if corpus else 0} "
                f"fps={len(corpus.fingerprints) if corpus else 0} "
                f"since_new={target.provider.since_new_behavior} "
                f"solver={bridge.stats.invocations if bridge else 0}",
                flush=True,
            )
            last_dbg = now

        # Optional solver invocation.
        if bridge is not None:
            bridge.maybe_run()

        if now - last_sample >= sample_interval:
            corpus = target.provider.corpus
            provider = target.provider
            sample = CoverageSample(
                elapsed=elapsed,
                iters=iters,
                behaviors=len(corpus.behavior_counts) if corpus else 0,
                fingerprints=len(corpus.fingerprints) if corpus else 0,
                since_new_behavior=provider.since_new_behavior,
                corpus_size=len(corpus.corpus) if corpus else 0,
                solver_invocations=bridge.stats.invocations if bridge else 0,
                solver_seeds=bridge.stats.seeds_proposed if bridge else 0,
            )
            result.samples.append(sample)
            last_sample = now

    final_elapsed = time.perf_counter() - start
    corpus = target.provider.corpus
    result.final_iters = iters
    result.final_elapsed = final_elapsed
    result.final_behaviors = len(corpus.behavior_counts) if corpus else 0
    result.final_fingerprints = len(corpus.fingerprints) if corpus else 0
    # snapshot DEEP_HITS for this run
    result.deep_branches_hit = dict(DEEP_HITS)
    if bridge is not None:
        result.solver_stats = bridge.stats.as_dict()
        result.solver_stats["_listener_events"] = _listener_stats["events"]
        result.solver_stats["_listener_forwarded"] = _listener_stats["forwarded"]
        result.solver_stats["_queue_depth_end"] = len(
            target.provider._choices_queue
        )
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--time-budget", type=float, default=60.0,
                   help="seconds per campaign (per mode)")
    p.add_argument("--stall-threshold", type=int, default=400)
    p.add_argument("--solver-budget", type=float, default=10.0)
    p.add_argument("--min-reinvoke", type=float, default=10.0,
                   help="don't invoke solver more often than this many seconds")
    p.add_argument("--target", default="deep_eq", choices=sorted(TARGETS))
    p.add_argument("--out-dir", default="/tmp/solver_demo")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--skip-baseline", action="store_true")
    p.add_argument("--skip-solver", action="store_true")
    args = p.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[RunResult] = []

    if not args.skip_baseline:
        print(f"[baseline] running {args.target} for {args.time_budget:.1f}s")
        results.append(run_campaign(
            args.target,
            time_budget=args.time_budget,
            use_solver=False,
            stall_threshold=args.stall_threshold,
            solver_budget_seconds=args.solver_budget,
            min_reinvoke_interval=args.min_reinvoke,
            seed=args.seed,
        ))
        print(f"  ... iters={results[-1].final_iters} "
              f"behaviors={results[-1].final_behaviors} "
              f"fingerprints={results[-1].final_fingerprints}")
        print(f"  deep branches hit: {results[-1].deep_branches_hit}")

    if not args.skip_solver:
        print(f"[+solver] running {args.target} for {args.time_budget:.1f}s "
              f"(stall={args.stall_threshold}, solver_budget={args.solver_budget}s, "
              f"reinvoke>={args.min_reinvoke}s)")
        results.append(run_campaign(
            args.target,
            time_budget=args.time_budget,
            use_solver=True,
            stall_threshold=args.stall_threshold,
            solver_budget_seconds=args.solver_budget,
            min_reinvoke_interval=args.min_reinvoke,
            seed=args.seed,
        ))
        print(f"  ... iters={results[-1].final_iters} "
              f"behaviors={results[-1].final_behaviors} "
              f"fingerprints={results[-1].final_fingerprints}")
        print(f"  solver stats: {results[-1].solver_stats}")
        print(f"  deep branches hit: {results[-1].deep_branches_hit}")

    # Write CSV time-series
    for r in results:
        csv_path = out_dir / f"{args.target}_{r.mode}.csv"
        with csv_path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["elapsed_s", "iters", "behaviors", "fingerprints",
                        "since_new_behavior", "corpus_size",
                        "solver_invocations", "solver_seeds"])
            for s in r.samples:
                w.writerow(s.as_row())

    # Write JSON summary
    summary_path = out_dir / f"{args.target}_summary.json"
    summary_path.write_text(json.dumps(
        [r.as_summary() for r in results], indent=2
    ))
    print(f"\nwrote csv+json to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
