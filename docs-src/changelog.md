# Changelog
HypoFuzz uses [calendar-based versioning](https://calver.org/), with a
`YY-MM-patch` format.

Fixed compatibility with Pytest 8.1 ([#35](https://github.com/Zac-HD/hypofuzz/issues/35)).

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
