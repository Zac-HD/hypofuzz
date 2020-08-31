Development Roadmap
===================

Hypofuzz is both an active research project and a production-ready tool.

I believe that this dual nature is a strength for both: users get to leverage
a tool based on cutting-edge research, but also ensure that the problems it
solves are ones that really matter.  There's a lot of applied research out
there which never makes the translation to practice - and I don't intend to
add to it.


Compatibility Policy
--------------------

Hypofuzz uses `calendar-based versioning <https://calver.org/>`__, with a
``YY-MM-patch`` format.

Because Hypofuzz is closely tied to Hypothesis internals, we recommend pinning
your transitive dependencies using a tool like :pypi:`pip-compile <pip-tools>`,
:pypi:`poetry`, or :pypi:`pipenv`.  This makes it possible to reproduce old
environments based only on your VCS history, and ensures that any compatibility
problems in new releases can be handled when it suits you.


Direct Dependencies
~~~~~~~~~~~~~~~~~~~

Hypofuzz's direct dependencies are:

.. literalinclude:: ../setup.py
   :prepend: install_requires = [
   :start-after: install_requires=[
   :end-before: ],
   :append: ]


API Deprecation Policy
~~~~~~~~~~~~~~~~~~~~~~

Hypofuzz does not provide a Python API.

The command-line interface will not make incompatible changes without at least
three months notice, during which passing deprecated options will emit runtime
warnings (e.g. via the terminal, displayed on the dashboard, etc.).

Integration points with Hypothesis, such as the
:class:`~hypothesis:hypothesis.database.ExampleDatabase` API, are considered
stable upstream and are very unlikely to change.

If it is impractical to continue to support old versions of Hypothesis (or other
dependencies) after a major update, the minimum supported version will be updated.
If you would like to use new versions of Hypofuzz with old versions of its
dependencies, please get in touch to discuss your specific needs.


Planned Features
----------------

See :doc:`literature` for notes on where some these ideas come from.

.. note::

    This page is more a personal TODO note than a plan.
    Don't try to hold research outcomes to best intentions.


For each fuzz target
~~~~~~~~~~~~~~~~~~~~

- report failing examples in the dashboard - at least nodeid, ideally mimicing
  the whole output from Hypothesis with traceback + minimal example.


Better mutation logic
+++++++++++++++++++++

- improve our tracking of the input pool
- explicitly find the minimal example that covers each known branch?
  might be too small to mutate from...

- need to add some proper mutation operators to start with
- structure-aware crossover / replacement / splicing etc (MOpt)
- validity-aware mutations (Zest/RLCheck), based on structure
- Nezha-like differential coverage via dynamic contexts

    - could easily split out drawing examples from SUT code


Guiding towards what?
+++++++++++++++++++++

Typically, fuzzers haven't really been guided towards new arcs (src-dest branches)
as they have been good at exploiting them once found at random.  We can do that,
but we can probably also do better.

- prioritize under-explored arcs, afl-fast or fairfuzz style

- use CFG from :pypi:`coverage` to tell if new branches are actually available
  from a given path.  If not, we can hit it less often.
  Note that branch coverage != available bugs; the control flow graph is not
  identical to the behaviour partition of the program.

- perf-fuzz to maximise branch count(s) - would need upstream support from coverage

- fuzz arbitrary scores with :func:`hypothesis:hypothesis.target()` (see FuzzFactory)





Adaptive fuzzing of many targets
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- get multi-process fuzzing working

    - option to allow a target to run in multiple processes at once (off by default)
    - avoid locking in a single-machine implementation, scaling further (dask?) is good

- implement and characterise Pythia's predictions

- deal with memory use problem - will probably need to run each target for longer
  and dump (almost?) all state to disk between runs

- dealing with "substantially overlapping" test functions

    - do we use a similar inverse-stationary-distribution trick to afl-fast?
      because maybe only the assertions vary, and we need to run both (do we?)
    - means we'll be dealing with "arcs from any target" as well
      makes sense though, if only one test covers part of the SUT
      we probably do want to spend more compute on it.




User experience, workflow integration, monitoring
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- publish a bare-bones ``hypofuzz`` package on PyPI - goal is to have a public
  no-op implementation of any helpers, so that test suites can be run (not fuzzed)
  with only freely available libraries.
  Move logic to Hypothesis itself where that makes sense.

- user-facing documentation, examples, tips

- live dashboard for the overall campaign, and subpage for each target

- (maybe?) support non-pytest test suites

- exploit VCS metadata, i.e. target recently-changed parts of the SUT and
  new / recently changed tests (c.f. :pypi:`pypi-testmon`)

- sharing state / adaptive params across runs, for 'live at head' fuzzing

    - track corpus to go from cold start to adapted ASAP
    - (maybe later) ``git pull`` mode; regularly fetch a branch and
      crash+restart if there have been changes.

- must be zero configuration.  ask users to suggest heuristics/conventions
  instead of configure their instance.  You can select the targets; that's it.

- a "scaling hint" would be cool - get automatic estimates of current
  value per minute, and balance that against cost of compute and current
  change frequency to recommend number of cores to use.  (much later)
