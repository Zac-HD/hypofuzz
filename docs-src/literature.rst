Summary of related research
===========================

Hypofuzz is built on, and inspired by, a wide range of research and practice
in software testing and verification.  This page summarises selected parts
of that literature, with opinionated comments.

.. warning::

    This page is incomplete and disorganised.


TODO: add citations with https://sphinxcontrib-bibtex.readthedocs.io/en/latest/quickstart.html



Hypothesis & Property-based Testing
-----------------------------------

JOSS paper, David's ECOOP paper



Hypothesis is implemented around a bytestring representation for all
test cases.  All "strategies" (data generators) can transparently
generate random instances via a PRNG, or replay past test-cases by
substituting a recorded bytestring for the PRNG stream.

In short, we implement property-based testing as a structured fuzzer,
using a hybrid of every technique that seemed useful - thanks again
to our clean IR layer.

Our users are therefore used to writing fuzz harnesses which exercise
their code and check meaningful semantic properties, and indeed already
have hundreds or even thousands of such harnesses already written.



common to observe that PBT is fuzzing; also common to wish that PBT would
steal features from fuzzing engines.  Less common to wish that fuzzing
integrated into workflows as well as PBT does!

axes along which they typically differ

- PBT executes far fewer example inputs
- PBT expects to generate mostly valid inputs
- PBT is mostly used by developers; fuzzing mostly by later bug hunters



We solve 'fuzzer taming' with canonical minimal test inputs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Incidentally, this same IR layer enables better shrinking capabilities than
any other tool I know of, effectively solving the "fuzzer taming" problem.
In the production version of Hypothesis we distinguish errors by the type and
location of the exception, but the 'interesting origin' could trivially be
augumented or replaced with other metrics such as stack hashes if desired.

Key points include auto-pruning and automatic partial canonicalisation,
tracking the parse tree to enable an adaptive variant of heirarchal
delta-debugging, and sophisticated 'normalisation' which simplifies
as well as minimising the size of examples.  The result is a shortlex
K-minimal bytestring with respect to all our reduction operators.

Shrinking is properly the subject of David's research though, so for this
paper we will simply treat finding the canonical minimal input which causes
any distinct error as a solved problem.


We use a fast, blackbox backend to support testing workflows
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Hypothesis' primary use-case is as a library for writing property-based tests.
A typical run will execute a total of one hundred input test cases, including
replay of previous failures, and take a few hundred milliseconds.

This is, obviously, very different from a typical fuzzing campaign.

Our backend is therefore quite different from a coverage-guided fuzzer, as it
is adapted for minimal feedback and short, fast 'campaigns'.  Indeed, we
shipped experimental coverage guidance in 2018: the overhead was ~5x in a typical
case, or ~70x on PyPy (tracing logic is not good for the JIT compiler), and did
not typically pay off until several thousand test cases in.  We therefore removed
the feature as conceptually nice, but not worth the cost of maintainence for us
or the burden of extra documentation and config options for our users.

We use a combination of pure random generational fuzzing, with lightweight
mutation of previous examples - mostly by splicing them into a generated
stream in place of random bytes.  This boosts the probability of e.g. duplicate
list elements which would otherwise be incredibly rare, and helps us generate
data subject to difficult filters far more often than chance would suggest.

TODO mention targeted PBT here, contrasting PropEr with simulated annealing?
Or should we save that for later and point out that it has FuzzFactory built in?


'Strategies' are parser-combinators designed for structured fuzzing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Hypothesis users specify the allowed inputs to their test function by composing
"strategies", which are internally used to parse PRNG or replayed bytestrings
into valid data.

Users may compose strategies with arbitrary code, including code under test,
and they therefore comprise an unrestricted grammar which permits arbitrary
backwards dependencies.  In principle forward constraints are also possible,
but this works so poorly in practice that we can ignore the pathological case.

We nonetheless keep the grammar fairly local, to better support our splicing
and shrinking logic - for example, to generate a list we draw a 'should continue'
boolean before each element, rather than drawing a number of elements up-front.
Other such design tricks are documented in our implementers guide to 'strategies
which shrink' [ ref ].  This property also means that small changes in the
bytestring tend to correspond to small changes in the example.

Strategies are also designed such that, in the absence of user-defined filters,
most random bytestrings can be parsed into valid examples.  It's still a partial
function, but the builtin strategies work pretty well in practice.

They _also_ act as approximately idempotent transducers, such that parsing random
bytes will also output a partially canonicalised (shortlex leq) bytestring which
will reproduce the same example.  This only throws away 'obviously unused' parts
corresponding to e.g. rejection sampling, but is a nice boost to shrinking and
also to avoid calling user code with redundant inputs.

Our default backend, above, tracks a trie of known buffers.  Thanks to autopruning,
we can discard any proposed buffer which is known or has a known prefix as being
redundant.  Conversely if a proposal is a prefix of a known buffer it must not be
parseable, which can boost performance substantially during shrinking.



TODO: swarm testing, why it works, how we use it






Fuzzing
-------


Fuzz / Fuzz Revisited / Fuzz 2020
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

From the age of dinosaurs... proved that unguided random generational fuzzing
works.  "most of the bugs we found still there later" rings true, as does
"we gave away awesome tools and few people used them".


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
