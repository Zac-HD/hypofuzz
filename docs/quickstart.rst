Quickstart Guide
================


Prerequisites: :pypi:`pytest` & :pypi:`hypothesis`
--------------------------------------------------

HypoFuzz is designed to run :pypi:`hypothesis` tests, so you'll need some of
those as fuzz targets.

Our current implementation uses :pypi:`pytest` to collect the tests to run,
so you can select specific tests in the usual way by file, ``-k`` selectors,
or just allow pytest to discover all your tests for you.


Running :command:`hypothesis fuzz`
----------------------------------

Minimally configurable beyond test collection.
Number of processes to use (defaults to all cores).
Runs indefinitely until interrupted.

A web interface to monitor ongoing runs is planned.

The core idea is that while you run :command:`pytest ...` on each change,
you leave :command:`hypothesis fuzz ...` running constantly and *restart it*
on each change.  The hypofuzz engine will keep running tests and


Now what?  Reproducing and fixing bugs
--------------------------------------

HypoFuzz saves any failures it finds into Hypothesis' standard example
database, so the workflow for deduplicating and reproducing any failures
is "run your test suite in the usual way".

It really is that easy!


A quick glance under the hood
-----------------------------

HypoFuzz isn't "better" than Hypothesis - it's playing a different game,
and the main difference is that it runs for much longer.  That means:

- The performance overhead of coverage instrumentation pays off, as we can
  tell when inputs do something unusual and spend more time generating similar
  things in future.

- Instead of running 100 examples for each test before moving on to the next,
  we can interleave them, run different numbers of examples for each test, and
  focus on the ones where we're discovering new behaviours fastest.

We spend our time generating more interesting examples, focussed on the most
complex tests, and do so *without any human input at all*.
