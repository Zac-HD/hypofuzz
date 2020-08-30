Configuration
=============


It's all automatic
------------------

Wherever possible, Hypofuzz is designed to do the right thing without configuration.

:command:`hypothesis fuzz` accepts arguments to determine parameters like the
number of processes to use, and the port on which to serve the dashboard -
though every one of them is optional - and you can select which tests to fuzz
in the same way you would select them via :pypi:`pytest`.

Once that's all set up though, the fuzzer is not configurable: manual prioritization
of a fuzzing process is considerably more error-prone than allowing the adaptive
scheduler to do its thing, and computer time is much cheaper than yours.

If the fuzzer is missing something, please get in touch so we can improve the
heuristics and feeback mechanisms - and benefit everyone, automatically.



The Hypothesis Database
-----------------------

The hypothesis database forms the basis of Hypofuzz workflows: failing examples
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

TODO: write a ``RedisExampleDatabase``; plus others by client request.


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
