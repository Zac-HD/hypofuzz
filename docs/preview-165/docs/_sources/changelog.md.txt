# Changelog
HypoFuzz uses [calendar-based versioning](https://calver.org/), with a
`YY-MM-patch` format.

(v25-06-03)=
## 25.06.03

* Add new display options for the test coverage graph: `Together`, `Separate`, and `Latest`.
  * `Together` shows a linearized view of all workers for this test, even when they were concurrent in practice.
  * `Separate` shows each worker run for this test individually.
  * `Latest` shows only the latest worker for this test.
* Improve coverage calculation, to make reporting unstable coverage (due to e.g. caching) less likely. In the future, we will report coverage stability on the dashboard as a per-test percentage.

(v25-06-02)=
## 25.06.02

* Add a dashboard notification while the dashboard process is still loading reports from the database
* Improve the display of covering and failing patches on the dashboard

(v25-06-01)=
## 25.06.01

Substantial improvements to the dashboard UI and coverage tracking. Most notably:

* The dashboard now includes [Hypothesis observability](https://hypothesis.readthedocs.io/en/latest/reference/internals.html#observability), showing details about what inputs passed or failed an [`assume`](https://hypothesis.readthedocs.io/en/latest/reference/api.html#hypothesis.assume) statement, custom [`event`](https://hypothesis.readthedocs.io/en/latest/reference/api.html#hypothesis.event) occurrences, and more.
* HypoFuzz now separately tracks coverage of "Behaviors" (branches, [`event`](https://hypothesis.readthedocs.io/en/latest/reference/api.html#hypothesis.event), etc) and "Fingerprints" (unique sets of behaviors).

(v25-05-01)=
## 25.05.01

Improve assignment of tests to fuzz workers, and bundle version-specific docs with the dashboard.

(v25-04-10)=
## 25.04.10

Improve test table ui on mobile.

(v25-04-9)=
## 25.04.9

Also filter the coverage graph when filtering the test table, and fix failures for parametrized tests being written to the incorrect database key.

(v25-04-8)=
## 25.04.8

Improve text alignment of the test table UI.

(v25-04-7)=
## 25.04.7

Improve test table UI by using icons for most columns.

(v25-04-6)=
## 25.04.6

Improve mobile appearance, and add ability to filter table rows by string, for example to filter for all tests whose name contains a string.

(v25-04-5)=
## 25.04.5

Remove integration with the time-travel debugger [pytrace](https://pytrace.com/). While (very) cool in principle, the ecosystem is not yet mature or stable enough.

(v25-04-4)=
## 25.04.4

Tables in the dashboard can now be sorted by column.

(v25-04-3)=
## 25.04.3

The coverage graph in the dashboard now displays a more unified view across restarts, avoiding displaying dramatic drops in coverage when replaying the covering corpus.

(v25-04-2)=
## 25.04.2

Improve table UI in the dashboard.

(v25-04-1)=
## 25.04.1

Hypofuzz now uses a more accurate method of measuring branch coverage on python 3.12+, resulting in better fuzzing performance in general.

(v25-03-3)=
## 25.03.3

* Add a new `/collected` page, which shows which tests were skipped during pytest collection, and why.

(v25-03-2)=
## 25.03.2

* Add ability to zoom coverage graphs on the dashboard by scrolling. Double click to reset.
* Fix initial database state not being loaded when starting the dashboard.

(v25-03-1)=
## 25.03.1

Internal code formatting with no behavioral changes.

(v25-02-5)=
## 25.02.5

We now use the new [pub-sub database interface in Hypothesis](https://hypothesis.readthedocs.io/en/latest/changes.html#v6-126-0) to update the dashboard. Dashboard updates should be significantly more responsive and use less resources.

This release is not compatible with old hypofuzz databases.

(v25-02-4)=
## 25.02.4

Fix dashboard not getting properly built for pypi releases.

(v25-02-3)=
## 25.02.3

Overhaul of the dashboard UI.

(v25-02-2)=
## 25.02.2

Initial support for [stateful tests](https://hypothesis.readthedocs.io/en/latest/stateful.html).

(v25-02-1)=
## 25.02.1

Use a new mutator based on the typed choice sequence (https://github.com/HypothesisWorks/hypothesis/issues/3921), bringing back compatibility with new Hypothesis versions.

We also now ignore code coverage inside the `pytest` and `_pytest` modules, which is unhelpful to fuzz.

(v25-01-6)=
## 25.01.6

Pin upper Hypothesis bound for compatibility, until we support new Hypothesis internals.

(v25-01-5)=
## 25.01.5

Support for `@pytest.mark.skip` and `@pytest.mark.skipif`, and initial support for `@pytest.mark.parametrize`.

Also bumps Hypothesis to [6.124.0](https://hypothesis.readthedocs.io/en/latest/changes.html#v6.124.0), to support the new database format.

(v25-01-4)=
## 25.01.4

Ignore standard library and dynamically generated code for coverage.

(v25-01-3)=
## 25.01.3

Support collecting tests with a pytest autouse fixture that itself requests a non-autouse fixture.

(v25-01-2)=
## 25.01.2

Hypofuzz now uses [`sys.monitoring`](https://docs.python.org/3/library/sys.monitoring.html) for coverage instrumentation on python 3.12+, resulting in considerable speedups for recent python versions.

Also optimized database disk usage.


Requires [Hypothesis 6.123.12](https://hypothesis.readthedocs.io/en/latest/changes.html#v6.123.12)
or newer, for a race condition fix which Hypofuzz is liable to hit.

(v25-01-1)=
## 25.01.1

The dashboard now respects the current setting profile's database when loading fuzzing progress.
Use `settings.register_profile` and `settings.load_profile` to control the dashboard database.

You can also now pass `--port 0` to request an arbitrary open port for the dashboard.

(v24-11-1)=
## 24.11.1
The dashboard can now be run independently of fuzzing worker processes, with metadata for
display stored in Hypothesis' database instead of ephemeral state.  This makes horizontal
scalability very very easy, if you use e.g. the Redis database backend.

Requires [Hypothesis 6.121](https://hypothesis.readthedocs.io/en/latest/changes.html#v6-121-0)
or newer, so that those database writes happen in a background thread rather than blocking.

(v24-09-1)=
## 24.09.1
Fixed compatibility with Pytest 8.1 ([#35](https://github.com/Zac-HD/hypofuzz/issues/35)).
Requires [Hypothesis 6.103](https://hypothesis.readthedocs.io/en/latest/changes.html#v6-103-0)
or newer, for compatibility with the new and improved shrinker.

(v24-02-3)=
## 24.02.3
Fixed compatibility with Pytest 8.0 ([#32](https://github.com/Zac-HD/hypofuzz/issues/32)).

(v24-02-2)=
## 24.02.2
Fixed a dashboard bug ([#31](https://github.com/Zac-HD/hypofuzz/issues/31)).

(v24-02-1)=
## 24.02.1
Now requires [Hypothesis 6.93.2](https://hypothesis.readthedocs.io/en/latest/changes.html#v6-93-2)
or later, fixing compatibility with some unstable internals that HypoFuzz hooks into (yes, again).
Also deduplicates the displayed covering examples in the dashboard, when their reprs are identical.

(v23-12-1)=
## 23.12.1
Now requires [Hypothesis 6.91](https://hypothesis.readthedocs.io/en/latest/changes.html#v6-91-0)
or later, fixing compatibility with some unstable internals that HypoFuzz hooks into.

(v23-07-1)=
## 23.07.1
Various small patches for issues found by fuzzing Hypothesis itself.
Notably, we now try to fuzz functions which require autouse fixtures
even though we don't provide those fixtures - it often works!

(v23-06-1)=
## 23.06.1
Hypofuzz now writes ``.patch`` files with failing examples, *and* optionally
with covering examples - including removal of redundant covering examples.

(v23-05-3)=
## 23.05.3
Yet another compatibility fix for explain mode, with even _more_ tests for future regressions.
Third time lucky, we hope!

(v23-05-2)=
## 23.05.2
Additional compatibility fix, and improved tests to avoid future regressions.

(v23-05-1)=
## 23.05.1
Now requires [Hypothesis 6.75.2](https://hypothesis.readthedocs.io/en/latest/changes.html#v6-75-2)
or later, fixing compatibility with some unstable internals that HypoFuzz hooks into.

(v23-04-1)=
## 23.04.1
Fixed a bug affecting traceback reporting on Python 3.10+ (#16).

(v22-12-1)=
## 22.12.1
Fixed a `NotImplementedError` when HypoFuzz had found a failing input for *every*
test running in some process.  Now, we cleanly `sys.exit(1)` instead.

(v22-10-1)=
## 22.10.1
First open-source release!  Also improves database handling and adds
a timelimit to shrinking to better handle pathological cases.

(v22-07-1)=
## 22.07.1
Fixes compatibility with [Hypothesis 6.49.1](https://hypothesis.readthedocs.io/en/latest/changes.html#v6-49-1)
and later (released July 5th).

(v21-12-2)=
## 21.12.2
Web-based time-travel debugging with [PyTrace](https://pytrace.com/) - just
`pip install hypofuzz[pytrace]` and click the link on any failing test!

(v21-12-1)=
## 21.12.1
Improved dashboard (again!), better generation/mutation heuristics,
basic residual-risk estimation, free-for-noncommercial-use on PyPI.

(v21-05-1)=
## 21.05.1
Improved dashboard, fixed memory leaks, support arbitary `hypothesis.event()`
calls as coverage, performance improvements.

(v20-09-1)=
## 20.09.1
Multiprocess fuzzing with seed sharing and corpus distillation,
and basic prioritisation of seeds covering rare branches.

Still very much in alpha, but the fundamentals all work now.

(v20-08-1)=
## 20.08.1
First packaged version of HypoFuzz
