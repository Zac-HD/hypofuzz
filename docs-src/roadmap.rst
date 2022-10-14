Development roadmap
===================

HypoFuzz is both a research project and a production-ready tool.

We believe that this dual nature is a strength for both: users get to leverage
a tool based on cutting-edge research, but also ensure that the problems it
solves are ones that really matter.  There's a lot of applied research out
there which never makes the translation to practice - and we don't intend to
add to it.


Compatibility policy
--------------------

HypoFuzz uses `calendar-based versioning <https://calver.org/>`__, with a
``YY-MM-patch`` format.

Because HypoFuzz is closely tied to Hypothesis internals, we recommend pinning
your transitive dependencies using a tool like :pypi:`pip-compile <pip-tools>`,
:pypi:`poetry`, or :pypi:`pipenv`.  This makes it possible to reproduce old
environments based only on your VCS history, and ensures that any compatibility
problems in new releases can be handled when it suits you.


Direct dependencies
~~~~~~~~~~~~~~~~~~~

HypoFuzz's direct dependencies are:

.. literalinclude:: ../setup.py
   :prepend: install_requires = [
   :start-after: install_requires=[
   :end-before: ],
   :append: ]


API deprecation policy
~~~~~~~~~~~~~~~~~~~~~~

The command-line interface will not make incompatible changes without at least
three months notice, during which passing deprecated options will emit runtime
warnings (e.g. via the terminal, displayed on the dashboard, etc.).

User-accesible integration points with Hypothesis, such as the
:class:`~hypothesis:hypothesis.database.ExampleDatabase` API, are considered
stable upstream and are unlikely to change even in major version releases.

If it is impractical to continue to support old versions of Hypothesis (or other
dependencies) after a major update, the minimum supported version will be updated.
If you would like to use new versions of HypoFuzz with old versions of its
dependencies, please get in touch to discuss your specific needs.


Planned features
----------------

See :doc:`literature` for notes on where some these ideas come from.

.. note::

    While we're interested in the features described below, HypoFuzz remains
    a research project and plans may change as new information comes to light.
    Please `get in touch <mailto:hello@hypofuzz.com>`__ to let us know which you
    would prioritize, or if we're missing something important to you.


Architecture overhaul
~~~~~~~~~~~~~~~~~~~~~
I'm seriously considering going 'full distributed system' for Hypofuzz, by using
persistent state in the database as the coordination mechanism instead of http.

Currently: you launch ``hypothesis fuzz``, that starts n_cores worker processes
plus one to serve the dashboard, and UI data is streamed over JSON-over-HTTP.
This is basically fine, but you have to recover all your state by replaying saved
examples on every restart, the dashboard is tied to the worker processes, and you
can't scale up or down (or even really out beyond a single node).

But... we do have this handy Hypothesis database, which is without-loss-of-generality
a distributed database mapping bytes to set-of-bytes (e.g. using Redis, S3, whatever).
So why don't we just communicate via DB state instead of HTTP?

- The dashboard then works independently of how many (if any) worker processes
  are currently fuzzing, because it's just a presentation layer over the database.
- I can persist all the which-branches-discovered-when metadata and get much
  more accurate estimates of residual risk.  This should include provenance -
  from black/grey/whitebox - and needs to account for concurrent executions.
- Oh no. I'd hoped to avoid this but finally have a problem which actually
  calls for distributed consensus algorithms.  (fortunately I think this is simpler than Paxos...)
- The data model becomes much more complicated; some state might be from e.g.
  an earlier or unconnected commit.  Any notion of "the current code" is now local
  to the dashboard, so failing examples (etc) have to be replayed in the dashboard
  process - unless the cached data was tagged with the same e.g. commit hash -
  or else the text of the reports also needs to be stored in the database.
  Not to mention HypoFuzz itself updating...
- Oh, and the whole thing had better support fuzzing multiple repos or packages
  with a single database, so let's add another layer of namespacing.
- The main trick is to define exactly what data we need to store, and then use some
  CRDT-style technique to allow concurrent reads and writes. Or a git-style tree?
  Alternatively we could treat this as strictly-speculative and just throw out
  anything we can't linearize...

On the upside, the net effect of this design is that we'll be able to just throw things
into whatever autoscaling setup is convenient, and the overall system will continue
to make progress as nodes come and go.


Workflow and development lifecycle
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- expand user-facing documentation, examples, tips, etc.

- better reporting of test collection, e.g. tests skipped due to use of fixtures

- warn about tests where found examples can't be replayed because of settings
  decorator with derandomize=True or database=None; recommend profiles instead

- support collecting tests with ``unittest`` as well as pytest

- exploit VCS metadata, i.e. target recently-changed parts of the SUT and
  new / recently changed tests (c.f. :pypi:`pypi-testmon`)


Monitoring and reporting
~~~~~~~~~~~~~~~~~~~~~~~~

The `current dashboard <https://hypofuzz.com/example-dashboard/>`__ is a good
start, but there's plenty of room for improvement.

Main wishlist item: good support for starting the dashboard and worker processes
separately - especially with the architecture overhaul above.

We should also report coverage stability fraction, including a rating
stable (100%), unstable (85%--100%), or serious problem (<85%");
and explain the difference between stability=coverage and flakiness=outcome.


Observability ideas
+++++++++++++++++++

- Cuumulative and per-input coverage reports like :command:`coverage html`
- Compare branch-hit frequency between blackbox and mutational modes, to assist
  in designing strategies (inspired by `this blog post
  <https://hexgolems.com/2020/08/on-measuring-and-visualizing-fuzzer-performance/>`__).
- `Abstracting away inputs <https://youtu.be/Wy7qY5ms3qY?t=2058>`__ like
  e.g. `gamozolabs/cookie_dough <https://github.com/gamozolabs/cookie_dough>`__


Fuzzing machinery
~~~~~~~~~~~~~~~~~

- experiment with `slipcover <https://github.com/plasma-umass/slipcover>`__ - if the
  overhead of adding instrumentation is low, this could be a big win - and amortized
  across many unlikely-to-find-new-branches executions anyway if not.
- implement `predictive fuzzing like Pythia <https://github.com/mboehme/pythia>`__,
  and use that for prioritization (currently number of inputs since last discovery)
- (maybe) support moving targets between processes; could be more efficient in the
  limit but constrains scaling.  Randomised assignment on restart probably better.
  Easy-ish following architecture overhaul.
- Construct a 'dictionary' of known-interesting values based on extracting constants
  from the code under test, to generate more often than chance.
- Investigate Redqueen-style tracking, e.g. "a string in the input matched against this
  regex pattern in the code, so try generating from that" as the advanced version.


Better mutation logic
+++++++++++++++++++++

- structure-aware operators for crossover / replacement / splicing etc
- validity-aware mutations (Zest/RLCheck), based on structure
- Nezha-like differential coverage via dynamic contexts


Guiding towards what?
+++++++++++++++++++++

Typically, fuzzers haven't really been guided towards inputs which improve branch
coverage, as they have been good at exploiting them once found at random.
We can do that, but we can probably also do better.

- use CFG from :pypi:`coverage` to tell if new branches are actually available
  from a given path.  If not, we can hit it less often.
  Note that branch coverage != available bugs; the control flow graph is not
  identical to the behaviour partition of the program.

- try using a custom trace function, investigate performance and use of alternative
  coverage metrics (e.g. length-n path segments, callstack-aware coverage, etc.)

- fuzz arbitrary scores with :func:`hypothesis:hypothesis.target()` (see FuzzFactory)
