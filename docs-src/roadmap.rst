Development roadmap
===================

HypoFuzz is both an active research project and a production-ready tool.

I believe that this dual nature is a strength for both: users get to leverage
a tool based on cutting-edge research, but also ensure that the problems it
solves are ones that really matter.  There's a lot of applied research out
there which never makes the translation to practice - and I don't intend to
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
    Please `get in touch <mailto:hypofuzz@zhd.dev>`__ to let us know which you
    would prioritize, or if we're missing something important to you.


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
Note that the web version does not show elapsed time, or the details page for
each test.

Main wishlist item: good support for starting the dashboard and worker processes
separately.


Observability ideas
+++++++++++++++++++

- Cuumulative and per-input coverage reports like :command:`coverage html`
- Compare branch-hit frequency between blackbox and mutational modes, to assist
  in designing strategies (inspired by `this blog post
  <https://hexgolems.com/2020/08/on-measuring-and-visualizing-fuzzer-performance/>`__).
- `Abstracting away inputs <https://youtu.be/Wy7qY5ms3qY?t=2058>`__ like
  e.g. `gamozolabs/cookie_dough <https://github.com/gamozolabs/cookie_dough>`__
- integrate a time-travelling debugger like https://pytrace.com/


Fuzzing machinery
~~~~~~~~~~~~~~~~~

- implement `predictive fuzzing like Pythia <https://github.com/mboehme/pythia>`__,
  and use that for prioritization (currently number of inputs since last discovery)
- (maybe) support moving targets between processes; could be more efficient in the
  limit but constrains scaling.  Randomised assignment on restart probably better.


Better mutation logic
+++++++++++++++++++++

- structure-aware operators for crossover / replacement / splicing etc
- validity-aware mutations (Zest/RLCheck), based on structure
- Nezha-like differential coverage via dynamic contexts


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

- try using a custom trace function, investigate performance and use of alternative
  coverage metrics (e.g. length-n path segments, callstack-aware coverage, etc.)

- fuzz arbitrary scores with :func:`hypothesis:hypothesis.target()` (see FuzzFactory)
