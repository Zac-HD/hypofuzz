Features
========

The core principle of HypoFuzz is that it should be effortless to adopt:
if you have Hypothesis tests, everything else is automatic.  If you're
curious about what that "everything else" involves, this page is for you.

Execution model
---------------

HypoFuzz runs as one or more worker processes, by default one per available
core, and an additional process serving the live dashboard as a website.

In each worker process, HypoFuzz prioritizes tests which discover new coverage,
which maximises the rate of discovery and therefore minimises the time taken
to cover each branch in your code.  This adaptive approach is one of HypoFuzz's
advantages over other fuzzing workflows - and the reason you can apply it to
a whole test suite at a time.


HypoFuzz dashboard
------------------

The HypoFuzz dashboard - `online demo here <../../example-dashboard/>`__ - shows
the current state of the fuzzing campaign overall, with a sub-page for each test
to show more information.


Fuzzer details
--------------

HypoFuzz is, compared to other fuzzers in the literature, a bizzare mixture of
every technique that seems to work.  Instead of being based on "one brilliant
idea" (oversimplifying, AFL = "coverage-guided mutation", :cite:`AFLFast`
=  "bias towards rare branches", etc.), we have a single simple goal:
*fuzzing your property-based test suite should be effortless*.

Because HypoFuzz is designed to exploit features that already exist in Hypothesis,
you *can* write tests which are designed to be fuzzed, but idiomatic ``@given``
tests already work just fine.


Basic design
~~~~~~~~~~~~

It's a standard feedback-directed greybox fuzzer.  The interesting parts are

1. HypoFuzz tests Python code, not native executables
2. we exploit property-based tests to detect semantic bugs, not just crashes
3. we use Hypothesis to generate highly-structured and typically valid data
4. we leverage a wider variety of feedbacks than most fuzzers
5. we fuzz *very many* more targets than most fuzzing campaigns


Corpus distillation
~~~~~~~~~~~~~~~~~~~

We exploit Hypothesis' world-class test-case reduction logic ("shrinking") to
maintain a seed pool of minimal covering examples for each branch - or other
reason to retain a seed.

Those other reasons include user-defined labels via :func:`hypothesis:hypothesis.event`,
real-valued metrics with :func:`hypothesis:hypothesis.target`,
and more to come.


Mutation logic
~~~~~~~~~~~~~~

The mutation logic is minimum-viable at the moment.  It works shockingly well,
thanks to Hypothesis' input structure, but substantial improvements are on the
roadmap.


Ensemble fuzzing
~~~~~~~~~~~~~~~~

HypoFuzz natively supports ensemble fuzzing :cite:`EnFuzz`, by periodically loading
any new examples from the database.  This works in ``--unsafe`` mode, where each
test function might run in multiple fuzzer processes at the same time, and with
other fuzzer tools leveraging e.g. the `.hypothesis.fuzz_one_input
<https://hypothesis.readthedocs.io/en/latest/details.html#use-with-external-fuzzers>`__
hook.

Ensemble fuzzing can also be modelled as a mixture of the ensembled behaviours,
and HypoFuzz therefore attempts to run an *adaptive* mixture of all the useful
behaviours we can implement.  To the extent that this works, we get the benefits
of ensembling and consume the minimum possible resources to required to do so.


A glance under the hood
-----------------------

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
