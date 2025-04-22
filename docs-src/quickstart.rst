Quickstart guide
================


Prerequisites: :pypi:`pytest` & :pypi:`hypothesis`
--------------------------------------------------

HypoFuzz is designed to run :pypi:`hypothesis` tests, so you'll need some of
those as fuzz targets.

Our current implementation uses :pypi:`pytest` to collect the tests to run,
so you can select specific tests in the usual way by file, ``-k`` selectors,
or just allow pytest to discover all your tests for you.


Installation
------------

HypoFuzz is a pure-Python package, and can be installed from your shell with

.. code-block:: shell

    pip install hypofuzz

or from a ``requirements.txt`` file like

.. code-block:: text

    ...
    hypofuzz >= 21.05.1
    ...


Running :command:`hypothesis fuzz`
----------------------------------

The core idea is that while you run :command:`pytest ...` on each change,
you run :command:`hypothesis fuzz ...` on a server - and it'll keep searching
for interesting new inputs until shut down from outside.

.. command-output:: hypothesis fuzz --help

By design, this is minimally configurable: test selection and collection is
handled by ``pytest``, using exactly the same syntax as usual, and the
remaining options are out of scope for the fuzzer itself to determine.


Reproducing and fixing bugs
---------------------------

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
