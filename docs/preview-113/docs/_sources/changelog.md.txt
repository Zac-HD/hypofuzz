# Changelog
HypoFuzz uses [calendar-based versioning](https://calver.org/), with a
`YY-MM-patch` format.

## 25.06.01

Substantial improvements to the dashboard UI and coverage tracking. Most notably:

* The dashboard now includes [Hypothesis observability](https://hypothesis.readthedocs.io/en/latest/reference/internals.html#observability), showing details about what inputs passed or failed an [`assume`](https://hypothesis.readthedocs.io/en/latest/reference/api.html#hypothesis.assume) statement, custom [`event`](https://hypothesis.readthedocs.io/en/latest/reference/api.html#hypothesis.event) occurrences, and more.
* HypoFuzz now separately tracks coverage of "Behaviors" (branches, [`event`](https://hypothesis.readthedocs.io/en/latest/reference/api.html#hypothesis.event), etc) and "Fingerprints" (unique sets of behaviors).

## 25.05.01

Improve assignment of tests to fuzz workers, and bundle version-specific docs with the dashboard.

## 25.04.10

Improve test table ui on mobile.

## 25.04.9

Also filter the coverage graph when filtering the test table, and fix failures for parametrized tests being written to the incorrect database key.

## 25.04.8

Improve text alignment of the test table UI.

## 25.04.7

Improve test table UI by using icons for most columns.

## 25.04.6

Improve mobile appearance, and add ability to filter table rows by string, for example to filter for all tests whose name contains a string.

## 25.04.5

Remove integration with the time-travel debugger [pytrace](https://pytrace.com/). While (very) cool in principle, the ecosystem is not yet mature or stable enough.

## 25.04.4

Tables in the dashboard can now be sorted by column.

## 25.04.3

The coverage graph in the dashboard now displays a more unified view across restarts, avoiding displaying dramatic drops in coverage when replaying the covering corpus.

## 25.04.2

Improve table UI in the dashboard.

## 25.04.1

Hypofuzz now uses a more accurate method of measuring branch coverage on python 3.12+, resulting in better fuzzing performance in general.

## 25.03.3

* Add a new `/collected` page, which shows which tests were skipped during pytest collection, and why.

## 25.03.2

* Add ability to zoom coverage graphs on the dashboard by scrolling. Double click to reset.
* Fix initial database state not being loaded when starting the dashboard.

## 25.03.1

Internal code formatting with no behavioral changes.

## 25.02.5

We now use the new [pub-sub database interface in Hypothesis](https://hypothesis.readthedocs.io/en/latest/changes.html#v6-126-0) to update the dashboard. Dashboard updates should be significantly more responsive and use less resources.

This release is not compatible with old hypofuzz databases.

## 25.02.4

Fix dashboard not getting properly built for pypi releases.

## 25.02.3

Overhaul of the dashboard UI.

## 25.02.2

Initial support for [stateful tests](https://hypothesis.readthedocs.io/en/latest/stateful.html).

## 25.02.1

Use a new mutator based on the typed choice sequence (https://github.com/HypothesisWorks/hypothesis/issues/3921), bringing back compatibility with new Hypothesis versions.

We also now ignore code coverage inside the `pytest` and `_pytest` modules, which is unhelpful to fuzz.

## 25.01.6

Pin upper Hypothesis bound for compatibility, until we support new Hypothesis internals.

## 25.01.5

Support for `@pytest.mark.skip` and `@pytest.mark.skipif`, and initial support for `@pytest.mark.parametrize`.

Also bumps Hypothesis to [6.124.0](https://hypothesis.readthedocs.io/en/latest/changes.html#v6.124.0), to support the new database format.

## 25.01.4

Ignore standard library and dynamically generated code for coverage.

## 25.01.3

Support collecting tests with a pytest autouse fixture that itself requests a non-autouse fixture.

## 25.01.2

Hypofuzz now uses [`sys.monitoring`](https://docs.python.org/3/library/sys.monitoring.html) for coverage instrumentation on python 3.12+, resulting in considerable speedups for recent python versions.

Also optimized database disk usage.


Requires [Hypothesis 6.123.12](https://hypothesis.readthedocs.io/en/latest/changes.html#v6.123.12)
or newer, for a race condition fix which Hypofuzz is liable to hit.

## 25.01.1

The dashboard now respects the current setting profile's database when loading fuzzing progress.
Use `settings.register_profile` and `settings.load_profile` to control the dashboard database.

You can also now pass `--port 0` to request an arbitrary open port for the dashboard.

## 24.11.1
The dashboard can now be run independently of fuzzing worker processes, with metadata for
display stored in Hypothesis' database instead of ephemeral state.  This makes horizontal
scalability very very easy, if you use e.g. the Redis database backend.

Requires [Hypothesis 6.121](https://hypothesis.readthedocs.io/en/latest/changes.html#v6-121-0)
or newer, so that those database writes happen in a background thread rather than blocking.

## 24.09.1
Fixed compatibility with Pytest 8.1 ([#35](https://github.com/Zac-HD/hypofuzz/issues/35)).
Requires [Hypothesis 6.103](https://hypothesis.readthedocs.io/en/latest/changes.html#v6-103-0)
or newer, for compatibility with the new and improved shrinker.

## 24.02.3
Fixed compatibility with Pytest 8.0 ([#32](https://github.com/Zac-HD/hypofuzz/issues/32)).

## 24.02.2
Fixed a dashboard bug ([#31](https://github.com/Zac-HD/hypofuzz/issues/31)).

## 24.02.1
Now requires [Hypothesis 6.93.2](https://hypothesis.readthedocs.io/en/latest/changes.html#v6-93-2)
or later, fixing compatibility with some unstable internals that HypoFuzz hooks into (yes, again).
Also deduplicates the displayed covering examples in the dashboard, when their reprs are identical.

## 23.12.1
Now requires [Hypothesis 6.91](https://hypothesis.readthedocs.io/en/latest/changes.html#v6-91-0)
or later, fixing compatibility with some unstable internals that HypoFuzz hooks into.

## 23.07.1
Various small patches for issues found by fuzzing Hypothesis itself.
Notably, we now try to fuzz functions which require autouse fixtures
even though we don't provide those fixtures - it often works!

## 23.06.1
Hypofuzz now writes ``.patch`` files with failing examples, *and* optionally
with covering examples - including removal of redundant covering examples.

## 23.05.3
Yet another compatibility fix for explain mode, with even _more_ tests for future regressions.
Third time lucky, we hope!

## 23.05.2
Additional compatibility fix, and improved tests to avoid future regressions.

## 23.05.1
Now requires [Hypothesis 6.75.2](https://hypothesis.readthedocs.io/en/latest/changes.html#v6-75-2)
or later, fixing compatibility with some unstable internals that HypoFuzz hooks into.

## 23.04.1
Fixed a bug affecting traceback reporting on Python 3.10+ (#16).

## 22.12.1
Fixed a `NotImplementedError` when HypoFuzz had found a failing input for *every*
test running in some process.  Now, we cleanly `sys.exit(1)` instead.

## 22.10.1
First open-source release!  Also improves database handling and adds
a timelimit to shrinking to better handle pathological cases.

## 22.07.1
Fixes compatibility with [Hypothesis 6.49.1](https://hypothesis.readthedocs.io/en/latest/changes.html#v6-49-1)
and later (released July 5th).

## 21.12.2
Web-based time-travel debugging with [PyTrace](https://pytrace.com/) - just
`pip install hypofuzz[pytrace]` and click the link on any failing test!

## 21.12.1
Improved dashboard (again!), better generation/mutation heuristics,
basic residual-risk estimation, free-for-noncommercial-use on PyPI.

## 21.05.1
Improved dashboard, fixed memory leaks, support arbitary `hypothesis.event()`
calls as coverage, performance improvements.

## 20.09.1
Multiprocess fuzzing with seed sharing and corpus distillation,
and basic prioritisation of seeds covering rare branches.

Still very much in alpha, but the fundamentals all work now.

## 20.08.1
First packaged version of HypoFuzz
