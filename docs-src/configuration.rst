Configuration
=============

.. contents::
    :local:


It's all automatic
------------------

Wherever possible, HypoFuzz is designed to do the right thing without configuration.

The :command:`hypothesis fuzz` CLI accepts arguments to determine parameters like the
number of processes to use, and the port on which to serve the dashboard -
though every one of them is optional - and you can select which tests to fuzz
in the same way you would select them via :pypi:`pytest`.

Once that's all set up though, the fuzzer is not configurable: manual prioritization
of a fuzzing process is considerably more error-prone than allowing the adaptive
scheduler to do its thing, and computer time is much cheaper than yours.



Custom coverage events
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



The Hypothesis database
-----------------------

The Hypothesis database forms the basis of HypoFuzz workflows: failing examples
can be reproduced automatically just by running the tests - because those inputs
are added to the database and replayed by Hypothesis itself.

It is therefore critical that the fuzzer is using the *same* database as
Hypothesis - regardless of how or where you run it.

:hydocs:`Hypothesis' default database <database.html>` is designed to persist
failing examples on a single developer's machine, and does so via the filesystem.
If you want to share the database between your team members and your CI server
though, this isn't going to work so well - either set the
:obj:`~hypothesis:hypothesis.settings.database` setting to an
:class:`~hypothesis:hypothesis.database.ExampleDatabase` backed by a network
datastore, or use a :class:`~hypothesis:hypothesis.database.DirectoryBasedExampleDatabase`
pointed to a shared filesystem.
