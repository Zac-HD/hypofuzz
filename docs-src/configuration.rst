Configuration
=============

.. contents::
    :local:


It's all automatic
------------------

Wherever possible, HypoFuzz is designed to do the right thing without configuration.

:command:`hypothesis fuzz` accepts arguments to determine parameters like the
number of processes to use, and the port on which to serve the dashboard -
though every one of them is optional - and you can select which tests to fuzz
in the same way you would select them via :pypi:`pytest`.

Once that's all set up though, the fuzzer is not configurable: manual prioritization
of a fuzzing process is considerably more error-prone than allowing the adaptive
scheduler to do its thing, and computer time is much cheaper than yours.

If the fuzzer is missing something, please get in touch so we can improve the
heuristics and feeback mechanisms - and benefit everyone, automatically.



Custom Coverage Events
----------------------

HypoFuzz runs :pypi:`coverage` on every input to observe the branch coverage of your
code - but we know that there are many things code can do that aren't captured by
the set of executed branches.  `This blog post
<https://blog.foretellix.com/2016/12/23/verification-coverage-and-maximization-the-big-picture/>`__
gives a good overview of coverage-driven verification workflows.

We therefore treat each :func:`hypothesis.event` as a "virtual" branch - while it's
not part of the control-flow graph, we keep track of inputs which produced each
observed event in the same way that we track the inputs which produce each branch.

You can therefore use the :func:`~hypothesis.event` function in your tests to
mark out categories of behaviour, boundary conditions, and so on, and then let the
fuzzer exploit that to generate more diverse and better-targeted inputs.
And as a bonus, you'll get useful summary statistics when running Hypothesis!



The Hypothesis Database
-----------------------

The hypothesis database forms the basis of HypoFuzz workflows: failing examples
can be reproduced automatically just by running the tests - because those inputs
are added to the database and replayed by hypothesis itself.

It is therefore critical that the fuzzer is using the *same* database as
hypothesis - regardless of how or where you run it.


Writing a custom ExampleDatabase
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:hydocs:`Hypothesis' default database <database.html>` is designed to persist
failing examples on a single developer's machine, and does so via the filesystem.
If you want to share the database between your team members and your CI server
though, this isn't going to work so well.  Fortunately, it's pretty easy to
specify a database which *will* work.

The first option is to use Hypothesis's built-in
:class:`~hypothesis:hypothesis.database.DirectoryBasedExampleDatabase`,
and explicitly pass a path to a shared or synced directory.
This is easy to set up, but network drives have the usual performance issues
and you may not want to read and write so very many small files.

The second is to implement a custom :class:`~hypothesis:hypothesis.database.ExampleDatabase`
on top of your preferred key-value store - just ``save``, ``delete``, and ``fetch``
bytestrings - and use that instead.

.. TODO: write a ``RedisExampleDatabase``; plus others by client request.

Testing your custom ExampleDatabase
+++++++++++++++++++++++++++++++++++

HypoFuzz ships with a :hydocs:`Hypothesis state machine <stateful.html>` designed
to test that custom databases implement the same semantics as the builtin classes.

.. autoclass:: hypofuzz.database.DatabaseComparison


Multiplexed and Read-Only Databases
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Sometimes, you want to read from a central database without also writing to it.
Maybe you're testing a feature branch and don't want to save inputs to the same
database as master, or you want local machines to persist fuzzing state - but
not the the fuzz server.

The ``MultiplexedDatabase`` and ``ReadOnlyDatabase`` helpers are all you need.

.. autoclass:: hypofuzz.database.MultiplexedDatabase
.. autoclass:: hypofuzz.database.ReadOnlyDatabase


Copying the default database
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you've already started a fuzzing run, don't panic - you can copy the relevant
examples from the existing database to a new one with the following recipe:

.. code-block:: python

    import hypothesis

    hypothesis.settings.register_profile(
        "my-profile",
        database=MultiplexedDatabase(
            TheDatabaseYouWant(),
            ReadOnlyDatabase(hypothesis.settings.default.database),
        ),
    )
    hypothesis.settings.load_profile("my-profile")

Running the fuzzer with this :hydocs:`settings profile <settings.html#default-settings>`
active will copy all the used examples from the previous default database into
your preferred database.

This is essentially the same pattern that we recommend for teams: have a shared
database which can only be written to by the fuzz server, and allow CI jobs and
development machines read-only access to it.
