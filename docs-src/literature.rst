Summary of related research
===========================

HypoFuzz is built on, and inspired by, a wide range of research and practice
in software testing and verification.  This page summarises selected parts
of that literature, with opinionated comments.


Hypothesis & Property-based Testing
-----------------------------------

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


PBT is Structured Fuzzing
~~~~~~~~~~~~~~~~~~~~~~~~~

It's common to observe that property-based testing (PBT) is conceptually
related to fuzzing - see for example Dan Luu's `AFL + QuickCheck = ?
<https://danluu.com/testing/>`__ or Nelson Elhage's `Property-Based Testing Is Fuzzing
<https://blog.nelhage.com/post/property-testing-is-fuzzing/>`__ and
`Property Testing Like AFL <https://blog.nelhage.com/post/property-testing-like-afl/>`__.
For an essay on the *differences*, see David MacIver's `What is Property-Based Testing
<https://hypothesis.works/articles/what-is-property-based-testing/>`__.

The core of Hypothesis in in fact a blackbox structure-aware fuzzer,
and of course HypoFuzz itself is a more traditional greybox fuzzer built
on our shared IR layer.  Three things make HypoFuzz different from tradional fuzzers.

1. HypoFuzz is designed to work with many more targets than most fuzzers -
   we operate on *test suites*, not single binaries.
2. Because we're fuzzing property-based tests, HypoFuzz looks for semantics
   errors - not just crashes - and can check properties that are only expected
   to hold for a subset of valid inputs.
3. It's designed to fit into your development cycle, and be used by developers -
   so that the bugs get caught *before* the code ships.



We solve 'fuzzer taming' with canonical minimal test inputs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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



Fuzzing
-------

*The Fuzzing Book* :cite:`fuzzingbook2019` is a fantastic introduction to
and overview of the field.  While many of the papers cited below may not be
relevant unless you're *implementing* a fuzzer like HypoFuzz, the book is
a great resource for anyone involved in software testing.

.. warning::

    The following sections are incomplete, disorganised, and unreferenced.


Fuzz / Fuzz Revisited / Fuzz 2020
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`Bart Miller's pioneering work on fuzzing <http://pages.cs.wisc.edu/~bart/fuzz/>`__
defined the field, and proved that unguided random fuzzing works scarily well.
From 1990 :cite:`Fuzz1990` to 1995 :cite:`FuzzRevisited`, and again in 2020 :cite:`Fuzz2020`,
the persistence of bugs which can be caught by such simple tools seems timeless.
As, frustratingly, does the very slow adoption of such tools - to have read this
far betrays your excellent taste, dear reader.


AFL (classic)
~~~~~~~~~~~~~

Pulls JPEGs out of thin air.  Shockingly effective; easier to use than previous
tooling, worked very well at the time.  Somewhat out of date now; has maintained
fork "AFL++" aflplus.plus

Blindly 'ratchets' through the path-space of the program, selecting inputs and
mutations uniformly at random (after an initial determistic phase).


LibFuzzer
~~~~~~~~~

Is much more similar to Hypothesis - typically runs in-process, part of dev
worlflows, etc.  Also I think it exits on first crash?  Hypothesis' fuzz_one_input
fuzzer integration point directly imitates libfuzzer / LLVMFuzzOneInput.


AFL-fast, fair-fuzz, ???
~~~~~~~~~~~~~~~~~~~~~~~~

Prioritize inputs which are under-explored.  Basic concept is similar to a multi-arm
bandit problem, though interestingly more difficult due to shifting and exhaustible
distributions.

There are some cases - no free lunch theorem of optimisation - where this under-performs
classic mode, but in expectation it's flat several times more effective; especially
in short runs.

Related ideas: see Zest / input diversity / JQF-fuzz (sp?); 'helping generative fuzzers
avoid looking where the light is good'


Guiding towards target branches
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

AFL-go (Marcel Bohme again!) and ToFU demonstrate that preferentially scheduling
things which cover 'closer' to branches we want to hit works pretty well.

Potentially useful to seek out uncovered branches once we've been fuzzing for a while,
as distinct from exploiting recently discovered branches?  Conceptually fair-fuzz
is about hammering under-executed bits whereas this is about finding new bits.

TOFU (Target-Oriented FUzzer) also exploits input structure and claims that this is
substantially responsible for it's ~40% improvement over afl-go.


When should I stop fuzzing?  Pythia and the scaling conjecture.
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Treating bugs / branches / whatever you fuzz for as a species discovery problem, you
can predict mean time to next bug etc.  Very useful for answering the question of
when to stop fuzzing - see Pythia.

This also has obvious-to-me application in allocating compute time across very many
fuzz targets - use an approximation of Thompson sampling to choose a target to execute,
as in multi-arm bandit.  Very unlikely to be optimal but if we're only trying for
adaptively better than status quo that's OK, especially since we don't need user
config to tell us anything (important design principle!  we should automate things
to ease adoption, and user guidance can be wrong anyway)

Marcel Bohme has demonstrated pretty solidly that discovering bugs with fuzzing
takes exponential time, which is about as principled as it gets for deciding to
stop because costs exceed expected benefits.
(side note: I should totally get in touch with Marcel and talk about this stuff)


Structure-aware mutation with AFL-smart
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Marcel Bohme again, this time using Peach grammars.  Hypothesis IR is probably better
for this anyway, we have a very detailed parse tree even if it's not strictly part
of the IR.  Implementation is pretty tied to our current internals though, that will
be a pain to fix and might wait for a later version.

For that matter Hypothesis mutation (splicing) is I think already structure-aware?


MOpt-AFL: adapt probability distribution over mutation operators for each target
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Apparently, and plausibly, this works well.  Might as well build it in.


FuzzFactory: adding domain-specific targets to AFL's goals.  See also PerfFuzz
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

i.e. expanding the set of things that trigger you to keep a seed beyond covering a new branch.

Hypothesis already does this with our target() functionality, and even keeps a pareto
front for multi-objective optimisation.  Why not build it into the fuzzer too?

PerfFuzz also seems useful here, as a particular case of FuzzFactory which tends to
find e.g. accidentally quadratic algorithms.  Maybe only if a deadline is set?


Zest, RLcheck, and property-based testing as semantic fuzzing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Lots of interesting stuff out of the team at UC Berkely here.  Basically proposed the
PBT-as-structured-fuzzing approach two years after Hypothesis shipped it (albeit without
coverage guidance).

They use it to make 'predicative' generators work; while Hypothesis prefers to be valid
by construction we could totally steal this trick and it would probably work a lot better
for us - see the section on strategies above.


Nezha - efficient differential testing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Track coverage maps for N targets togther, and drive up the diversity of coverage
rather than just per-target.  Several times more efficient than individual
targets and cross-executing inputs; would be nice to evaluate this.

Would be nice to provide a context manager that can be wrapped around arbitrary
calls.  It would _also_ be nice to provide Nezha-style differential testing between
Python versions and implementations, which raises some questions about the execution
model - i.e. it's probably not just "run N copies (and maybe sync corpus)" anymore.


Reducing coverage overhead by rewriting the target
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

See "full-speed fuzzing", Nagy and Hicks.  The basic idea is that instead of paying
the perf overhead of tracing every input, you replace uncovered branches with an
interrupt.  When one fires, run that same input against your unmodified binary and
undo the patch!

They find huge speedups, since it converges to no (~0.3%) overhead a while in once
all the easy branches are covered.  Plausibly similar for Python (better on PyPy?).
In practice I think we'd want to use standard coverage for a while until new branches
are rare (see Pythia!), and then switch over.

Integrating this with the domain-specific targeting could be tricky; I suspect we'd
want branches and domain targets in separate maps / pareto fronts.  Also kinda hard
to think about calling into C extensions or whatever, but that applies to any coverage
tool in Python.


Ensemble fuzzing with seed sharing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Works very well in practice, but what other fuzzers are you going to run in Python?

OK, there's python-afl and pythonfuzz, I guess, but I want to just be flat better
than both.  crosshair-tool (SMT) integration would be pretty cool though, if we
could get it to inter-operate with Hypothesis IR.  That's SF though, at least for now...

Concretely, this suggests that using diverse algorithms would also be valuable as a way
of getting 'unstuck'.  Obvious next question is adaptive scheduling of this too...


Structure-aware fuzzing
~~~~~~~~~~~~~~~~~~~~~~~

Requires quite a lot of work elsewhere, e.g. Google has invested a lot of time in
protobuf-based fuzzing (because of course they have).

Hypothesis includes structured fuzzing for free, of course, with a slight skew.
Upside, we design our parsers for a heuristically bug-finding distribution, and
have some tricks to take this even further like swarm testing.
Downside, we can't convert an external corpus into our own format.

(this would be a really really nice tool to have, though - it can't work universally,
but might be worth the engineering work for the core strategies at least)



References
----------

.. bibliography:: literature.bib


