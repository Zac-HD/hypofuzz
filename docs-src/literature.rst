Summary of related research
===========================

HypoFuzz is built on, and inspired by, a wide range of research and practice
in software testing and verification.  This page summarises selected parts
of that literature, with opinionated comments.

.. contents::
    :local:


*The Fuzzing Book* :cite:`fuzzingbook2019` is a fantastic introduction to
and overview of the field.  While many of the papers cited below may not be
relevant unless you're *implementing* a fuzzer like HypoFuzz, the book is
a great resource for anyone involved in software testing.


Fuzzing background
------------------

Fuzz / Fuzz Revisited / Fuzz 2020
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`Bart Miller's pioneering work on fuzzing <http://pages.cs.wisc.edu/-bart/fuzz/>`__
defined the field, and proved that unguided random fuzzing works scarily well.
From 1990 :cite:`Fuzz1990` to 1995 :cite:`FuzzRevisited`, and again in 2020 :cite:`Fuzz2020`,
the persistence of bugs which can be caught by such simple tools seems timeless.
Unfortunately, so does the very slow adoption of such tools - if you're reading
this sentence, you have unusual (and excellent!) taste in testing technologies.


AFL (classic)
~~~~~~~~~~~~~

`Pulling JPEGs out of thin air
<https://lcamtuf.blogspot.com/2014/11/pulling-jpegs-out-of-thin-air.html>`__ made
a splash: `ALF <https://lcamtuf.coredump.cx/afl/>`__ was the first fuzzer tool
to reach mainstream awareness, and its success - measured in important bugs rather
than citations or benchmarks - revitalised the field.

The key insights were that lightweight instrumentation for coverage guided fuzzing
would often outperform fancier but slower techniques, and that usability counts -
with almost no configuration and a robust design applicable to any project,
AFL saw much wider adoption and therefore impact than previous tools.

Since 2017, `AFL~~ has been maintained by the community <https://aflplus.plus/>`__
with a variety of bugfixes, patches, and additional features many of which are
covered below.


LibFuzzer
~~~~~~~~~

`LibFuzzer <https://llvm.org/docs/LibFuzzer.html>`__ targets functions, rather than
whole binaries, and typically runs in-process.
:hydocs:`Hypothesis' .fuzz_one_input <details.html#use-with-external-fuzzers>`
function is directly inspired by the ``LLVMFuzzOneInput`` entry point, though
Hypothesis tests have much more sophisticated support for `structured fuzzing
<https://github.com/google/fuzzing/blob/master/docs/structure-aware-fuzzing.md>`__.



Property-based testing
----------------------

It's common to observe that property-based testing (PBT) is conceptually
related to fuzzing - see for example Dan Luu's `AFL ~ QuickCheck = ?
<https://danluu.com/testing/>`__ or Nelson Elhage's `Property-Based Testing Is Fuzzing
<https://blog.nelhage.com/post/property-testing-is-fuzzing/>`__ and
`Property Testing Like AFL <https://blog.nelhage.com/post/property-testing-like-afl/>`__.
For an essay on the *differences*, see David MacIver's `What is Property-Based Testing
<https://hypothesis.works/articles/what-is-property-based-testing/>`__.

The core of Hypothesis in in fact a blackbox structure-aware fuzzer,
and of course HypoFuzz itself is a greybox fuzzer built on our shared
IR layer.  Three things make HypoFuzz different from tradional fuzzers.

1. HypoFuzz is designed to work with many more targets than most fuzzers -
   we operate on *test suites*, not single binaries.
2. Because we're fuzzing property-based tests, HypoFuzz looks for semantics
   errors - not just crashes - and can check properties that are only expected
   to hold for a subset of valid inputs.
3. It's designed to fit into your development cycle, and be used by developers -
   so that the bugs get caught *before* the code ships.

Hypothesis
~~~~~~~~~~

Hypothesis :cite:`MacIver2019` is implemented around a bytestring representation for all
test cases.  All "strategies" (data generators) can transparently
generate random instances via a PRNG, or replay past test-cases by
substituting a recorded bytestring for the PRNG stream.

:cite:`MacIver2020` goes into more depth about the design of this IR layer,
and in particular how it enables efficient test-case reduction and normalisation.
This is the key to reporting minimal and de-duplicated failing examples, and
makes using a fuzzer much more productive (and less frustrating).

The IR layer has also proven invaluable as a clean and universal interface
to support other techniques such as targeted property-based testing
:cite:`TargetedPBT` - we get to automate (:cite:`AutomatingTargetedPBT`)
the setup for free, and support multi-dimensional optimisation into the
bargain.  See :func:`hypothesis:hypothesis.target` for details.


'Fuzzer taming' with test-case reduction
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Because Hypothesis presents a single `reduced
<https://blog.trailofbits.com/2019/11/11/test-case-reduction/>`__ and normalised
:cite:`OneTestToRuleThemAll` failing input for each unique exception type and location,
HypoFuzz largely avoids the `fuzzer taming problem <https://blog.regehr.org/archives/925>`__
:cite:`TamingCompilerFuzzers`.


'Strategies' are parser-combinators designed for structured fuzzing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Hypothesis users specify the allowed inputs to their test function by composing
"strategies", which are internally used to parse PRNG or replayed bytestrings
into valid data.  Users may compose strategies with arbitrary code, including code
under test, but while in principle this leads to an unrestricted grammar the
structure is usually tractable (`see here for some details
<https://github.com/HypothesisWorks/hypothesis/blob/master/guides/strategies-that-shrink.rst>`__).

Strategies are also designed such that, in the absence of user-defined filters,
most random bytestrings can be parsed into valid examples - which makes it easy
to support a hybrid generational/mutational fuzzer.

Some also use `swarm testing <https://blog.regehr.org/archives/591>`__
:cite:`SwarmTesting`, which improves the diversity of "weird" examples generated
without any user interaction at all.  Increasing our usage of this and
`other techniques <https://blog.regehr.org/archives/1700>`__ is an ongoing
project for Hypothesis.


Other property-based fuzzers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

(Java) junit-quickcheck + JQF + Zest + RLCheck
++++++++++++++++++++++++++++++++++++++++++++++

Starting with the ``junit-quickcheck`` library, `JQF <https://github.com/rohanpadhye/JQF>`__
:cite:`JQF` provides an interface to run property-based tests with a variety of fuzzing
backends including AFL, Zest :cite:`Zest` (adding validity metrics), and PerfFuzz.

`RLCheck <https://github.com/sameerreddy13/rlcheck>`__ :cite:`RLCheck` is distinctive
as a blackbox fuzzer, using reinforcement learning to generate valid inputs according
to some predicate.  While expressing constraints as predicates on a more general
input description is more natural for users, most PBT libraries require a constructive
approach to generation for acceptable performance - even when seriously unintuitive.


(Rust) proptest + propfuzz + propverify
+++++++++++++++++++++++++++++++++++++++

The `proptest <https://github.com/AltSysrq/proptest/>`__ library for Rust is directly
inspired by Hypothesis.  Showing the power of a good intermediate representation,
recent tools have built on top of this to provide both `fuzzing
<https://github.com/facebookincubator/propfuzz>`__ and `formal verification
<https://github.com/project-oak/rust-verification-tools>`__ with (almost) the same
user-facing API.

I'd *like* to support the latter too - e.g. via :pypi:`crosshair-tool` - but sadly
Python is a much harder target than machine code for symbolic verification and this
is more like science fiction than a roadmap item.


Mutation operators
------------------

Structure-aware mutation with AFLSmart
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

AFLSmart :cite:`AFLSmart` proposes using "smart mutation operators", specifically
adding, deleting, or replacing chunks of one seed input with corresponding chunks
of another input.  They find that this is a substantial improvement over
structure-naive converage-guided fuzzing, and that (as you'd expect) adding
feedback offers a very large improvement over blackbox generational fuzzing.

While they use `"Peach pits" <https://www.peach.tech/products/peach-fuzzer/peach-pits/>`__
to define the input grammar - and as the blackbox baseline - we can get the same
structural information directly from instrumentation in the Hypothesis internals
without any additional work for users or implementors.

Note that *structure-aware mutation* is a different technique to what is often
called *structure-aware fuzzing* (e.g. `here
<https://github.com/google/fuzzing/blob/master/docs/structure-aware-fuzzing.md>`__)
- the latter is simply a parsing step to allow e.g. classic AFL to operate on
structured data, and Hypothesis gives us a well-tuned version of that for free.


Adaptive mutation operator selection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`MOpt-AFL <https://github.com/puppet-meteor/MOpt-AFL>`__ :cite:`MOpt-AFL` finds that
the effectiveness of mutation strategies varies by target, and evaluates an adaptive
algorithm to customise the mutation logic accordingly.

TOFU :cite:`TOFU` varies the weighting of mutation operators with distance to the
goal; preferring large (add, delete, splice, etc.) operations while distant and small
(e.g. bitflip) when closer.



Scheduling inputs
-----------------

AFLFast & FairFuzz
~~~~~~~~~~~~~~~~~~

AFLFast :cite:`AFLFast` and FairFuzz :cite:`FairFuzz` observe that some branches
are covered by a higher proportion of inputs than others - for example, code which
rejects invalid inputs is usually overrepresented.

When AFL-Fast selects an input to mutate, it biases the choice towards inputs which
execute rare branches - and finds both an order-of-magnitude performance improvement
and more bugs than previous approaches.  Technically, the trick is to represent
the probability of covering each branch from a random mutation of each input as a
Markov chain, and then using the inverse of the stationary distribution as our
choice weights.

FairFuzz shares the goal of increasing coverage of rare branches, but does so by
detecting regions of the input which may be required to do so and disabling
mutations of those regions.  Their evaluation finds that this noticeably improves
coverage on code with deeply nested conditionals, against a baseline which includes
an early version of AFL-Fast (``-explore`` schedule added in 2.33, evaulation uses
2.40, ``-fast`` schedule seems to be best).


Directed fuzzing
~~~~~~~~~~~~~~~~

A `directed fuzzer <https://github.com/strongcourage/awesome-directed-fuzzing>`__,
such as `AFL-go <https://github.com/aflgo/aflgo>`__ :cite:`AFLgo`, prioritizes inputs
which are 'closer' to a target location.  This can be used to focus on recently-changed
code paths, areas flagged as bug-prone by static analysis, functions seen in logged
errors to reproduce a crash, etc.
TOFU :cite:`TOFU` also exploits input structure, and claims that this is substantially
responsible for it's -40% improvement over AFL-go.

HypoFuzz could get the control-flow graph from coverage.py, which tracks possible arcs
in order to report un-covered branches, so the implementation is straightforward.
The tradeoff between simplicity and power-requiring-configuration is less obvious;
I'm inclined to initially stick to zero-config direction towards recent patches and/or
lines flagged by e.g. :pypi:`flake8`; though the balance between directed and general
exploration might take some tuning.


Predictive fuzzing, scaling laws, & when to stop
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`Dr. Marcel Böhme <https://mboehme.github.io/>`__ has done groundbreaking work
characterising the behaviour of fuzzers (as well as co-creating AFLfast, AFLsmart,
and AFLgo!), in order to understand the assurances that fuzzing can provide and
quantify the residual risk :cite:`AssuranceInTestingRoadmap`.

`Pythia <https://github.com/mboehme/pythia>`__ :cite:`STADS` adds statistical predictions
to AFL, including bounds on the probability of finding a bug, estimated progress towards
maximal coverage, and a difficulty metric.  These metrics are obviously of interest
to users, and can also be used to schedule those targets with the highest expected
value - maximising the overall rate of progress.

Applying this scheduling insight to seeds rather than targets yields `Entropic (preprint)
<https://mboehme.github.io/paper/FSE20.Entropy.pdf>`__, which prioritizes those seeds
which maximise the rate of discovery of new information about the behaviour of the
fuzzed program.  This shows `substantial improvement over baseline LibFuzzer
<https://www.fuzzbench.com/reports/2020-05-24/index.html>`__, and is now heavily used
by `OSS-Fuzz <https://google.github.io/oss-fuzz/>`__.

Finally, :cite:`ExponentialCost` describes empirical scaling laws for fuzzers -
spending more CPU time finds a given set of bugs or coverage proportionally faster,
but finding *new* or *additional* bugs or coverage requires exponentially more
computation.  This means that spending a little effort on very many targets is
often worthwhile, but simply throwing more compute at a given target is eventually
of limited value.  On the other hand, improving the fuzzer or diversifing its
behaviour is correspondingly very valuable for well-fuzzed targets!



Seed selection
--------------

Corpus distillation
~~~~~~~~~~~~~~~~~~~

Corpus distillation refers to the technique of selecting an appropriately minimal
subset of a large initial corpus which covers the same set of branches in the code
under test (``afl-cmin``, if you've used that).  While traditionally defined only
for coverage, this is trivially extensible to other metrics - just ensure that there
are no discarded inputs which would be kept if freshly discovered by the fuzzer.

While reducing (``afl-tmin``) and normalising inputs is also a known technique for
debugging, I haven't seen an evaluation of its use to prepare a seed corpus for
fuzzing.  Maintaining such a canonical minimal seed pool could plausibly be useful,
or alternatively it may turn out to discard too much information instead.

I intend to evaluate a validity-aware canonical seed pool approach on top of
appropriately smart mutation operators, and will link to results from here.


Nezha - efficient differential testing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`Nezha <https://github.com/nezha-dt/nezha>`__ :cite:`Nezha` provides efficient
differential testing, by taking the product of the coverage for each input fed
to multiple targets.

While the original AFL docs observed that a distilled corpus from one e.g. jpeg
library would often trigger bugs in another, as branches to handle edge cases select
for edge-case inputs which may be mishandled by the other, using joint instead of
independent coverage has similar advantages to that of ensemble fuzzing.

This is relatively easy to implement using :pypi:`coverage` dynamic contexts and
a context manager or decorator API *within a given process*; while I'd also like
to support differential coverage between Python versions or operating systems
that will require some deeper changes to HypoFuzz's execution model.


Domain-specific targets with FuzzFactory
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`FuzzFactory <https://github.com/rohanpadhye/FuzzFactory>`__ :cite:`FuzzFactory`
observes that coverage may not be the only metric of interest, and extends the feedback
mechanism in AFL to support user-specified labels.

This essentially brings targeted propety-based testing (above) to fuzzing workflows,
and provides prior art (outside Hypothesis' implementation) of the multi-objective
approach - finding that this is often much more effective than optimising component
metrics independently.



Miscellaneous
-------------

Reducing coverage overhead by rewriting the target
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Full-speed fuzzing :cite:`FullSpeedFuzzing` reduces the performance overhead of
coverage measurement by rewriting the target - because most executions do not find
new coverage, this allows you to instrument a very small proportion of executions.

While offering very impressive speedups, this doesn't support differential metrics
or non-coverage metrics, and the rewriting trick would be rather difficult - though
not impossible - in Python.  Augumenting PyPy's tracing JIT to report coverage
information would probably be more fruitful, and also very fast given the repeated
execution pattern of fuzzing.

See also: `Python Coverage could be fast
<https://www.drmaciver.com/2017/09/python-coverage-could-be-fast/>`__.


Ensemble fuzzing with seed sharing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

EnFuzz :cite:`EnFuzz` demonstrates that combining diverse fuzzers both improves their
joint performance (given equal resources), and makes the performance much more robust.
The argument that this works by allowing specialised fuzzers to build on each other's
work, including iteratively, is compelling.

It's less clear how to leverage this for HypoFuzz, since there aren't many other
fuzzers targeting Hypothesis tests.  You could use :pypi:`python-afl` or
:pypi:`pythonfuzz` on :hydocs:`.fuzz_one_input <details.html#use-with-external-fuzzers>`
if you were careful enough about the database location; I intend to evaluate this
approach but don't expect an advantage from adding structure-naive fuzzers.

I think the general lesson is more like that of swarm testing: diversity is the
key to effective fuzzing.  Knowing that in advance though, we can build our single
fuzzer to execute a mixture of the relevant behaviours with the desired distribution,
and even make that distribution adaptive with respect to each target.

At the science-fiction end of things, it *might* be possible to interoperate with
:pypi:`crosshair-tool` - a SMT-solver based whitebox fuzzer for Python - and
parse a restricted set of Python objects back into the IR which would generate
them from a given Hypothesis strategy.  That's nowhere near the roadmap, though.



References
----------

.. bibliography:: literature.bib
