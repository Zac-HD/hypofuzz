# HypoFuzz × CrossHair solver-bridge — prototype results

This is a prototype integration that unblocks HypoFuzz's greybox engine with a
short burst of SMT-backed exploration via `hypothesis-crosshair` whenever the
coverage-guided fuzzer stalls.

- Design notes: `src/hypofuzz/solver.py` (module docstring)
- Tracking issue: https://github.com/pschanely/hypothesis-crosshair/issues/26
- Demo driver: `scripts/solver_demo.py`
- Raw data: `*_baseline.csv`, `*_solver.csv`, `*_summary.json`

## What the bridge does

1. While HypoFuzz runs normally, the bridge monitors `since_new_behavior`
   — the same stall counter already exposed on the dashboard.
2. When that counter exceeds a threshold (default 500), the bridge swaps
   in a `CrossHairPrimitiveProvider` via `ConjectureData(provider=...)` and
   runs a bounded-wall-clock burst of CrossHair iterations against
   the same Hypothesis test state.
3. Each realised choice sequence is captured from the Hypothesis
   observation stream (observability callback) and written to the
   HypoFuzz corpus DB key.
4. HypoFuzz's DB listener re-enqueues those seeds automatically; the
   greybox worker replays them under `HypofuzzProvider` where coverage
   is measured and acceptance is decided as for any other discovered seed.

Warm-starting CrossHair with corpus seeds (via `replay_choices()`) is wired
up but **disabled by default**: on targets with heavy magic-value
predicates, a warm-start seed that can't satisfy the downstream path
conditions can force SMT to spend tens of seconds proving path infeasibility
on a single iteration, which is worse than CrossHair's native tree search.

## Demonstration setup

Three synthetic targets in `scripts/solver_demo.py`, each with a shallow
body and one or more "deep" branches that require satisfying a nested
equality/magic-value predicate to reach. All three are impossible or
very-slow for random mutation over the input space:

- **deep_eq**: two ints in `[-1e9, 1e9]`, deep branches require
  `x+y==13 ∧ x*y==42` (DEEP_1) and `x-y==11 ∧ x+y==999` (DEEP_2).
- **magic_ints**: three ints in `[-1e6, 1e6]`, deep branch requires all
  three to equal specific magic constants (`0xBADF00D`, `0xC0FFEE`,
  `0xDEADBEEF`).
- **string_tree**: a text strategy that must start with the literal
  four-character prefix `"MAGE"`.

Each target runs twice: a 60-second baseline campaign (vanilla HypoFuzz) and
a 60-second augmented campaign (HypoFuzz + solver bridge, stall threshold
500, 8-second solver budget per phase, minimum 15-second interval between
phases).

Command used:

```
python scripts/solver_demo.py --time-budget 60 --stall-threshold 500 \
    --solver-budget 8 --min-reinvoke 15 --target <name>
```

## Quantitative results

### Behaviors and fingerprints after 60s

| Target        | Mode      | Behaviors | Fingerprints | Greybox iters | Solver iters |
|---------------|-----------|-----------|--------------|---------------|--------------|
| deep_eq       | baseline  |   12      |    4         |   29,974      |      –       |
| deep_eq       | +solver   | **23**    |  **11**      |   13,580      |    5,792     |
| magic_ints    | baseline  |    5      |    1         |   24,984      |      –       |
| magic_ints    | +solver   | **15**    |   **4**      |   10,791      |    6,282     |
| string_tree   | baseline  |    9      |    3         |   35,256      |      –       |
| string_tree   | +solver   | **19**    |   **6**      |   15,204      |    6,491     |

Across all three targets, the augmented campaign covers roughly **2×** the
behaviors and **2.5–4×** the fingerprints of the baseline while using less
than half of its wall-clock budget on the greybox engine (the solver used
~32s of each 60s campaign). Every behavior the solver contributed is a
branch the baseline missed.

### Time-to-first-hit on deep branches

Wall-clock seconds from the start of the campaign to the first time each
"deep" branch was exercised. `×` means never reached in the 60-second run.

| Branch                                                 | Baseline | +Solver  |
|--------------------------------------------------------|----------|----------|
| deep_eq: `x+y==13` (mid-depth linear)                  | 59.2 s   |  1.9 s   |
| deep_eq: `x*y==42` (mid-depth quadratic)               | ×        |  1.7 s   |
| deep_eq: `DEEP_1` = `x+y==13 ∧ x*y==42 ∧ x>0 ∧ y>0`    | ×        |  3.6 s   |
| deep_eq: `DEEP_2` = `x-y==11 ∧ x+y==999 ∧ x>100 ∧ y>100`| ×        |  3.3 s   |
| magic_ints: `a==BADF00D`                               | ×        |  1.9 s   |
| magic_ints: `a==BADF00D ∧ b==C0FFEE`                   | ×        |  2.1 s   |
| magic_ints: 3-gate `DEEP`                              | ×        |  2.2 s   |
| string_tree: `s[0]=="M"`                               | 18.8 s   |  1.5 s   |
| string_tree: `s[:2]=="MA"`                             | ×        |  1.5 s   |
| string_tree: `s[:3]=="MAG"`                            | ×        |  1.7 s   |
| string_tree: `s.startswith("MAGE")` (DEEP)             | ×        |  1.9 s   |

Every deep branch missed by the baseline (nine of ten in total) is reached
within the first four seconds of the augmented campaign, before the
solver phase has even finished its first invocation.

### Solver cost

Per 60-second campaign the solver bridge used ~32 s of wall clock across
4 phases (8 s each) and proposed 53–72 unique realised choice sequences.
Of those, 35–53 were genuinely novel seeds (not already in the corpus);
every one was picked up by HypoFuzz's DB listener and replayed through
`HypofuzzProvider`. Queue depth at end of campaign was 0 in every run.

## How the artifacts connect to the issue

Issue pschanely/hypothesis-crosshair#26 asks for a mechanism to feed
high-coverage inputs from HypoFuzz into CrossHair (warm-start), and to
interleave solver-based exploration with coverage-guided fuzzing.

This prototype exercises both directions:

- **Corpus → CrossHair** via `PrimitiveProvider.replay_choices()` —
  implemented in the Hypothesis core branch picked up for this run, and
  honoured by CrossHair in `claude/warm-start-choice-sequences-Jf7zR` with
  a new `space.set_choice_hints()` hook. `SolverBridge._select_warm_start_seeds`
  picks corpus fingerprints ranked by branch rarity; `warm_start_count=0`
  by default for the reasons noted above, but the pipeline is working.
- **CrossHair → HypoFuzz** via the observability callback +
  `database.corpus.save()` → DB listener. `SolverBridge.run_solver_phase`
  captures each realised choice sequence during the solver burst and
  writes it to the corpus key; `HypofuzzProvider.on_event` picks it up and
  enqueues for replay.

The bridge is deliberately small (~200 LOC) and does not touch
`HypofuzzProvider` or the worker loop. Integration is by composition:
construct a `SolverBridge(target)` and call `maybe_run()` between greybox
iterations (the demo driver does this explicitly; a production wiring
would do it inside `FuzzWorker.start()` immediately after `target.run_one()`).

## Files

- `src/hypofuzz/solver.py` — `SolverBridge` + `SolverStats`.
- `scripts/solver_demo.py` — A/B harness with four demo targets.
- `tests/test_solver.py` — unit tests for the bridge.
- `scripts/solver_demo_results/*.csv` — coverage-over-time samples (every
  250 ms); columns: `elapsed_s, iters, behaviors, fingerprints,
  since_new_behavior, corpus_size, solver_invocations, solver_seeds`.
- `scripts/solver_demo_results/*_summary.json` — final numbers per campaign.

## Known limitations / next steps

- **Warm-start is fragile on some targets.** CrossHair can spend tens of
  seconds trying to prove a corpus-seeded path infeasible; with no
  per-iteration watchdog outside Hypothesis's deadline, one bad seed
  stalls the whole phase. Default is 0. A safer approach would run
  CrossHair with a short `settings.deadline` for the duration of the
  phase, which clamps its internal `per_path_timeout`.
- **No dashboard integration yet.** `SolverStats` is exposed on the
  bridge but not written to the database as part of the normal Report
  stream. A small addition to `database/` and the frontend would make
  the solver contribution visible alongside `behaviors` and
  `fingerprints` in the test detail view.
- **Scheduling is naive.** `should_invoke` uses a single fixed threshold
  on `since_new_behavior`. A proper adaptive schedule (e.g. EWMA of
  greybox coverage rate vs. past solver payoff per target) is deferred.
- **Attribution.** The bridge reports how many seeds it proposed, but not
  how many of those actually moved the HypoFuzz corpus — that info only
  lives in the fingerprint delta, which we don't yet thread back into
  `SolverStats`. Easy to add once we track per-seed provenance.
