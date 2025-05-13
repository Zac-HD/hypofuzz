Summary of related research
===========================

HypoFuzz is built on, and inspired by, a wide range of research and practice
in software testing and verification.  This page summarises and comments on
selected parts of that literature, focussing on papers which are in some sense
prior art for fuzzing property-based tests for Python.

.. tip::

    `See HypoFuzz in action here! <../example-dashboard/>`__

Fuzzing background
------------------

Fuzzers can generally be divided into two categories:

1. *Generational* fuzzers generate new inputs from scratch, using a random number
   generator to choose various options.  This covers everything from the simplest
   use of random numbers in a unit test, to highly sophisticated tools like
   CSmith :cite:`CSmith`.

2. *Mutational* fuzzers derive new inputs by mutating known inputs, and adding
   interesting examples to the 'pool' of known inputs.  Greybox mutational fuzzers
   reliabily find security vulnerabilities in almost any previously-unfuzzed C code,
   but are only rarely applied to search for semantic or non-security bugs.

Hypothesis takes a hybrid approach, using (mostly) generational fuzzing to find
failing examples, and then mutating and replaying an internal representation
to find the minimal failing example.
HypoFuzz takes a smarter approach by exploiting mutation-based example generation,
running a variety of instrumentation which is too expensive for sub-second unit
tests, and adapting the fuzzing logic to each test function as it learns.
More on this below.

*The Fuzzing Book* :cite:`fuzzingbook2019` is a fantastic introduction to
and overview of the field.  While many of the papers cited below may not be
relevant unless you're *implementing* a fuzzer like HypoFuzz, the book is
a great resource for anyone involved in software testing.


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
a splash: `AFL <https://lcamtuf.coredump.cx/afl/>`__ was the first fuzzer tool
to reach mainstream awareness, and its success - measured in important bugs rather
than citations or benchmarks - revitalised the field.

The key insights were that lightweight instrumentation for coverage guided fuzzing
would often outperform fancier but slower techniques, and that usability counts -
with almost no configuration and a robust design applicable to any project,
AFL saw much wider adoption and therefore impact than previous tools.

Since 2017, `AFL++ has been maintained by the community <https://aflplus.plus/>`__
:cite:`AFL++` with a variety of bugfixes, patches, and additional features - many of
which are covered below.


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
related to fuzzing - see for example Dan Luu's `AFL + QuickCheck = ?
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
recent tools have attempted to build on top of this to provide both `fuzzing
<https://github.com/facebookincubator/propfuzz>`__ and `formal verification
<https://github.com/project-oak/rust-verification-tools>`__ with (almost) the same
user-facing API.

Hypothesis supports symbolic execution via the :pypi:`hypothesis-crosshair`
:ref:`alternative backend <hypothesis:alternative-backends>`, and we plan to incorporate
this into HypoFuzz with an ensemble-style approach.

(C / C++) TrailofBits' DeepState, Google's ``fuzztest``
+++++++++++++++++++++++++++++++++++++++++++++++++++++++

`DeepState <https://github.com/trailofbits/deepstate>`__ :cite:`DeepState` provides
a common interface to various symbolic execution and fuzzing engines - write your
tests once with a Google Test-style API, and then run them with a variety of backends
and at various stages of your development cycle.

Google's `fuzztest <https://github.com/google/fuzztest>`__ library is described as
a tool that bridges the gap between fuzzing and property-based testing, allowing you
to write fuzz test side by side with regular unit tests.  ``fuzztest`` always runs
with coverage guidance, but is designed to be used as part of a testing (rather than
standard fuzzing) workflow.


(Haskell) QuickFuzz
+++++++++++++++++++

QuickFuzz :cite:`QuickFuzz` uses the venerable QuickCheck :cite:`QuickCheck` and
file format parsers from `Hackage <https://hackage.haskell.org/>`__ to implement
an unguided generational fuzzer.


(Coq) FuzzChick
+++++++++++++++

FuzzChick :cite:`FuzzChick` is a coverage-guided backed for QuickChick :cite:`QuickChick`,
a property-based testing library for the `Coq <https://en.wikipedia.org/wiki/Coq>`__
theorem prover.


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
Doing so will also give Hypothesis `better ways to explain why your test failed
<https://github.com/HypothesisWorks/hypothesis/issues/3411>`__ essentially for free.

Note that *structure-aware mutation* is a different technique to what is often
called *structure-aware fuzzing* (e.g. `here
<https://github.com/google/fuzzing/blob/master/docs/structure-aware-fuzzing.md>`__)
- the latter is simply a parsing step to allow e.g. classic AFL to operate on
structured data, and Hypothesis gives us a well-tuned version of that for free.


Adaptive mutation operator selection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`MOpt-AFL <https://github.com/puppet-meteor/MOpt-AFL>`__ :cite:`MOpt-AFL` finds that
the effectiveness of mutation strategies varies by target, and evaluates an adaptive
particle-swarm algorithm to customise the mutation logic accordingly.

:cite:`OneFuzzingStrategyToRuleThemAll` study "Havoc" mode, in which multiple
randomly-selected mutation operators are applied in a single step.  They find that
this typically outperforms a one-operator-at-a-time approach, and that dynamically
tuning the operator weights with a (non-stationary) multi-arm-bandit approach yields
further large improvements.

TOFU :cite:`TOFU` varies the weighting of mutation operators with distance to the
goal; preferring large (add, delete, splice, etc.) operations while distant and small
(e.g. bitflip) when closer.


Inputs from Hell
~~~~~~~~~~~~~~~~

:cite:`InputsFromHell` generates inputs matching a grammar, with a twist: by observing
the frequency with which various generation choices appear in a sample, you can
*invert* this distribution to instead generate dissimilar inputs.  While partly
subsumed by rare-branch-targeting tricks (under scheduling inputs, below), this trick
might also have some synergistic effects.



Scheduling inputs
-----------------

AFLFast, FairFuzz, and AlphaFuzz
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

AFLFast :cite:`AFLFast` and FairFuzz :cite:`FairFuzz` observe that some branches
are covered by a higher proportion of inputs than others - for example, code which
rejects invalid inputs is usually overrepresented.

When AFL-Fast selects an input to mutate, it biases the choice towards inputs which
execute rare branches - and finds both an order-of-magnitude performance improvement
and more bugs than previous approaches.  Technically, the trick is to represent
the probability of covering each branch from a random mutation of each input as a
Markov chain, and then using the inverse of the stationary distribution as our
choice weights.

AlphaFuzz :cite:`AlphaFuzz` observes that because mutation operators tend to make
local changes, modelling the lineage of each seed (again, as a Markov chain) further
improves on AFL-Fast by accounting for semantic diversity among seeds that reach
the same set of branches.  However, I doubt this would help HypoFuzz, given our
larger mutation steps and strong reduction and normalization of seeds.

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
:cite:`wang2020sok` survey the state-of-the-art in directed greybox fuzzing as of  mid-2020.

HypoFuzz could get the control-flow graph from coverage.py, which tracks possible branches
in order to report un-covered branches, so the implementation is straightforward.
The tradeoff between simplicity and power-requiring-configuration is less obvious;
we're inclined to initially stick to zero-config direction towards recent patches and/or
lines flagged by e.g. :pypi:`flake8`; though the balance between directed and general
exploration might take some tuning.

Directed swarm testing :cite:`DirectedSwarmTesting` takes a slightly different approach:
it is assumed that *some* randomly generated test cases will execute the target code,
and so the goal is to increase that proportion by biasing the swarm configuration
towards including 'trigger' features and omitting 'suppressors'.

SyML :cite:`SyMLPatternLearning` learn patterns among vulnerability-triggering paths
in known-buggy programs, and find that the learned features are predictive in unrelated
programs.  Originally motivated by mitigating path explosion in symbolic execution, it
seems equally applicable to directed fuzzing and could be a substantial advantage for
a centralized platform where there are more programs (and bugs) to learn from.


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

Applying this scheduling insight to seeds rather than targets yields Entropic
:cite:`Entropic`, which prioritizes those seeds
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

:cite:`Moonlight` evaluates a variety of approaches to designing input corpora,
given a typically much larger initial corpus (which might be `scraped from the internet
<https://security.googleblog.com/2011/08/fuzzing-at-scale.html>`__ or created with
a generative fuzzer), and finds that minimising both the number of inputs in the
seed pool and their cumulative size improves fuzzer performance - and that no
single approach dominates the others.

Reducing (:cite:`DeltaDebugging` or ``afl-tmin``) and normalising
(:cite:`OneTestToRuleThemAll`) failing test-cases is a well-known as technique
to assist in debugging, and supported - often called *shrinking* - by all good
property-based testing tools.  HypoFuzz uses Hypothesis' world-class test case
reduction to calculate the minimal example for each feature of interest - covered
branch, high score from :func:`hypothesis:hypothesis.target`, etc. - and uses
this as a basis for further fuzzing as well as reporting failing examples.

We are unaware of previous work which uses this approach or evaluates it in
comparison to less-intensive distillation.  We expect that it works very well
if-and-only-if combined with generative and structure-aware fuzzing, to allow
for exploitation of the covering structure without unduly standardising
unrelated parts of the input.


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
a context manager or decorator API *within a given process*; while we'd also like
to support differential coverage between Python versions or operating systems
that will require some deeper changes to HypoFuzz's execution model.


Domain-specific targets with FuzzFactory
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`FuzzFactory <https://github.com/rohanpadhye/FuzzFactory>`__ :cite:`FuzzFactory`
observes that coverage may not be the only metric of interest, and extends the feedback
mechanism in AFL to support user-specified labels.

This essentially brings targeted property-based testing (above) to fuzzing workflows,
and provides prior art (outside Hypothesis' implementation) of the multi-objective
approach - finding that this is often much more effective than optimising component
metrics independently.


Virtual branches with IJON
~~~~~~~~~~~~~~~~~~~~~~~~~~

`IJON <https://github.com/RUB-SysSec/ijon>`__ :cite:`IJON` adds custom feedback to
AFL.  The ``IJON_SET`` macro adds a 'virtual branch' based on the value passed, so
that at least one input exhibiting whatever custom behaviour will be retained in
the seed pool (HypoFuzz implements this with the :func:`hypothesis:hypothesis.event`
function).  The ``IJON_MAX`` macro is equivalent to :func:`hypothesis:hypothesis.target`,
similar to FuzzFactory above.

IJON is particularly notable for winning 29 out of 32 *Super Mario Bros* levels,
a feat more typical of dedicated reinforcement learning systems, as well as
fuzzing a Trusted Platform Module, complex format parsers, mazes, and a hash map.


Diversity
~~~~~~~~~

A key point here is that fuzzing and testing tools should search for *diverse* inputs,
to avoid getting trapped in a "optimal" but non-bug-finding state.  For example, IJON
optimized x-distance *at each distinct altitude* to avoid dead-ends.

Hypothesis tracks the :wikipedia:`pareto frontier <Pareto_front>` of metrics passed
to :func:`hypothesis.target` (plus some internal metrics).  For observable dimensions
where there is *not* a clear "best" direction and may be thousands of dimensions,
such as the hit-count of each branch, there are a variety of approaches.

AFL and related fuzzers "bucketize" the hitcount and then track uniqueness up to a
64k hash of this vector, as a compromise between performance (driven by CPU cache sizes)
and collision rate (typically 10-15% for library-like targets, but up to 75% for
larger applications :cite:`CollAFL`).

HypoFuzz's approach of keeping the best (shortlex-minimal) seed covering each branch
is reminiscent of SugarSearch :cite:`SugarSearch`; that paper opens with a lovely
survey of `quality-diversity algorithms <https://quality-diversity.github.io/>`__
algorithms - including CVT-MAP-elites :cite:`MAP-elites,CVT-MAP-elites`, which might
be nice to try for prioritization in high-dimensional spaces.

BeDivFuzz :cite:`BeDivFuzz` proposes measuring behavioural diversity using the
:wikipedia:`'Hill numbers' <Diversity_index>` from ecology; HypoFuzz already selects
seeds via (a mixed distribution including) sampling seeds in inverse proportion to
the observed frequency of the rarest branch covered by each.



Coverage
--------

Before diving in to the use of coverage information as feedback for test-case generation
in fuzzers, it's worth covering the use of code coverage in a software development cycle.

*How to Misuse Code Coverage* :cite:`HowToMisuseCoverage` still resonates:
"I wouldn't have written four coverage tools if I didn't think they're helpful.
But they're only helpful if they're used to *enhance* thought, not *replace* it.".
More than 20 years later, `code coverage best practices
<https://testing.googleblog.com/2020/08/code-coverage-best-practices.html>`__
from the Google Testing Blog gives similar advice.

*Coverage and its discontents* :cite:`CoverageDiscontents` explores the role of coverage
metrics in test-suite evaluation, and argues that there is an underlying uncertainty as
to what exactly measuring coverage should achieve, how we would know if it can, and what
we as researchers and developers can do about it.

`Verification, coverage and maximization: the big picture
<https://blog.foretellix.com/2016/12/23/verification-coverage-and-maximization-the-big-picture/>`__
aims to explain how coverage is used to optimize the verification process, what it means to
auto-maximize coverage, and how people have tried to do it - from a background in
hardware design, which brings an instructively different perspective to analogous problems.
(similar to Dan Luu's `AFL + QuickCheck = ? <https://danluu.com/testing/>`__, above)


Reducing coverage overhead by rewriting the target
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Full-speed fuzzing :cite:`FullSpeedFuzzing` reduces the performance overhead of
coverage measurement by rewriting the target - because most executions do not find
new coverage, this allows you to instrument a very small proportion of executions.

While offering very impressive speedups, this doesn't support differential metrics
or non-coverage metrics, and the rewriting trick would be rather difficult in Python.
Nonetheless, the `PLASMA-UMass <https://plasma-umass.org/>`__ team have released
`Slipcover <https://github.com/plasma-umass/slipcover>`__, a super-low-overhead
coverage tool for Python based on just this principle - and explicitly list fuzzing
as one of the applications.

Augumenting PyPy's tracing JIT to report coverage information would probably also be
fruitful, and very fast given the JIT-friendly repeated execution pattern of fuzzing.


Faster coverage measurement for Python
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

On Python 3.11 and earlier, coverage instrumentation uses :func:`python:sys.settrace`,
which has substantial overhead as it cannot be disabled after the first time a line or
branch executes. :pypi:`coverage` typically slows instrumented programs
by a factor of several times, typically ranging from 2-5x but with as much as 70x known
on some workloads.

Fortunately, on Python 3.12 and newer, :mod:`sys.monitoring` (via :pep:`669`) provides coverage
instrumentation at a much lower overhead. HypoFuzz uses ``sys.monitoring`` on 3.12+, and
falls back to ``sys.settrace`` on earlier Python versions.

Sensitive coverage metrics
~~~~~~~~~~~~~~~~~~~~~~~~~~

*Be Sensitive and Collaborative: Analyzing Impact of Coverage Metrics in Greybox Fuzzing*
:cite:`SensitiveAndCollaborative` compares a range of coverage metrics - from branch
coverage, to n-gram-coverage (chains of branches, when standard branch coverage is 2-gram),
full path coverage, and several others.  Due to resource limits - time, memory, compute -
no metric dominates all others, suggesting that adapting the metric per-target might
be helpful.


Compressing coverage information
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Ankou :cite:`Ankou` measures coverage of the *number of times* each branch was executed,
i.e. order-insensitive path coverage.  To manage the very large number of covering inputs,
they use a dynamic distance-based metric to retain only dissimilar inputs rather than
all covering inputs.  By comparison AFL bucketizes branch hit-counts.



Miscellaneous
-------------

Ensemble fuzzing with seed sharing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

EnFuzz :cite:`EnFuzz` demonstrates that combining diverse fuzzers both improves their
joint performance (given equal resources), and makes the performance much more robust.
The argument that this works by allowing specialised fuzzers to build on each other's
work, including iteratively, is compelling.

Cupid :cite:`Cupid` demonstrates significant practical advances in ensemble fuzzing,
defining a *complementarity* metric (union of the expected value of the set of covered
branches for each fuzzer).  This allows for efficient selection of fuzzers to be ensembled
based only on 'solo' runs of each.  Because Cupid leaves seed scheduling to future work
and is based on target-independent characterisation, this technique is used to design
HypoFuzz 'tactics' but not for runtime adaptation.

It's less clear how to leverage this for HypoFuzz, since there aren't many other
fuzzers targeting Hypothesis tests.  You could use :pypi:`python-afl`,
:pypi:`pythonfuzz`, or `python-hfuzz <https://github.com/thebabush/python-hfuzz>`__
on Hypothesis' :hydocs:`.fuzz_one_input <details.html#use-with-external-fuzzers>` hook
if you were careful enough about the database location; we intend to evaluate this
approach but don't expect an advantage from adding structure-naive fuzzers.

We think the general lesson is more like that of swarm testing: diversity is the
key to effective fuzzing.  Knowing that in advance though, we can build our single
fuzzer to execute a mixture of the relevant behaviours with the desired distribution,
and even make that distribution adaptive with respect to each target.


Hybrid concrete/symbolic fuzzing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This literature review has largely ignored symbolic execution, because support for
Python is at a very early stage and does not scale to real-world programs.

For native code, *concolic execution* - tools which combine concrete and symbolic
execution of tests - date back to DART :cite:`DART` and CUTE :cite:`CUTE` in 2005;
while Microsoft's SAGE :cite:`SAGE` found `roughly one-third of all the bugs
<https://queue.acm.org/detail.cfm?id=2094081>`__ discovered by file fuzzing during
the development of Windows 7 - running *after* static analysis and other fuzzers.

Inputs synthesised by symbolic or concolic approaches could provide the initial
seed pool for a classic mutational fuzzer, and provide a way to 'get unstuck'
on conditions which are hard to satisfy by chance.
Hypothesis supports symbolic execution via the :pypi:`hypothesis-crosshair`
:ref:`alternative backend <hypothesis:alternative-backends>`, and we plan to incorporate
this into HypoFuzz with an ensemble-style approach.


Scaling fuzzers up to many cores
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The `scaling behaviour of fuzzers is often neglected
<https://gamozolabs.github.io/2020/08/11/some_fuzzing_thoughts.html#scaling>`__,
which can make academic evaluations running on single cores misleading as users
in industry run campaigns on tens, hundreds, or even thousands of cores.
For example, classic AFL quickly (5-20 cores) bottlenecks on ``fork()``,
and adding more than 40 cores may *reduce total throughput*.
IO bottlenecks are also common in filesystem accesses for ensemble fuzzing campaigns.

:cite:`PAFL` finds that this problem is *worse* among more advanced fuzzers -
if you share seeds but not e.g. the branch hit-counts for AFL-Fast, each process
must duplicate the discovery process.  P-AFL adds a mechanism for global sharing
of guidance information as well as seeds, and additionally focusses each process
on fuzzing a subset of the branches in the program - which diversifies the search
process and effectively ensembles variants of a single base fuzzer.

We plan to mitigate this in HypoFuzz, by sharing ephemeral state between instances
and runs via the database.


Visualising fuzzer performance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

HypoFuzz does not offer many configuration options, but users are effectively
co-developers of the fuzzer because they provide the system under test, the
test function, and the strategies which define possible inputs.  Providing
clear and detailed - but not overwhelming - information about what the fuzzer
is doing can therefore support a wider feedback loop of improvement to the tests
and ultimately better bug-detection.

Brandon Falk's `some fuzzing thoughts
<https://gamozolabs.github.io/2020/08/11/some_fuzzing_thoughts.html>`__ points
out that a log-x-axis is almost always the right way to view fuzzer progress
graphs, especially considering the well-known exponential scaling curve
:cite:`ExponentialCost`.

Cornelius Aschermann's `on measuring and visualising fuzzer performance
<https://hexgolems.com/2020/08/on-measuring-and-visualizing-fuzzer-performance/>`__
suggests a range of other helpful visualisations, including the proportion of
inputs from various generation or mutation strategies which cover each known
branch.

*Evaluating Fuzz Testing* :cite:`EvaluatingFuzzTesting` investigates serious
problems in previous evaluations, and provides the now-canonical guidelines
for evaluating fuzzers.  Essential reading if you wish to publish an evaluation,
or simply decide whether some tweak was actually helpful without getting the
sign of the relationship wrong due to random noise.



References
----------

*While not all the referenced papers are open access, they
do all have freely accessible PDFs.  Enjoy!*

.. bibliography:: literature.bib
