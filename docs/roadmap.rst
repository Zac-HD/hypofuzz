Feature Roadmap
===============

Hypofuzz is both an active research project and a production-ready tool.

I believe that this dual nature is a strength for both: users get to leverage
a tool based on cutting-edge research, but also ensure that the problems it
solves are ones that really matter.  There's a lot of applied research out
there which never makes the translation to practice - and I don't intend to
add to it.


.. note::

    This page is more a personal TODO note than a plan.
    Don't try to hold research outcomes to best intentions.

See :doc:`literature` for notes on where some these ideas come from.


For each fuzz target
~~~~~~~~~~~~~~~~~~~~

- insert failing examples into standard Hypothesis database
- drop (or just deprioritze?) targets where we've seen a failure


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

- user-facing documentation, examples, tips

- live dashboard for the overall campaign, and subpage for each target

- (maybe?) support non-pytest test suites

- improve database docs + tooling upstream in Hypothesis,
  e.g. a "union" wrapper, "readonly" wrapper, etc. to share among a team

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


Commercialisation
~~~~~~~~~~~~~~~~~

Hypothesis is free and open-source software, and always will be.  It's useful
for businesses, community projects, and Python novices too.

Hypofuzz builds on this, but is disproportionately valuable for businesses
and probably out of scope for novice pythonistas.  I therefore intend to sell
commercial licences rather than open-sourcing it - though nonprofit open source
projects will be offered unlimited use for no charge.

Things to do here:

- website, email, docs, etc.  promotional materials, basically.
- work out pricing and business model

    - SAAS would be the classic option, but I really don't want to do ops.
    - can I just put it on PyPI and let people pay for legal right to use?

- set up through e.g. Stripe Atlas?





