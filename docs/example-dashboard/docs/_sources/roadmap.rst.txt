Development roadmap
===================

HypoFuzz is both a research project and a production-ready tool.

We believe that this dual nature is a strength for both: users get to leverage
a tool based on cutting-edge research, but also ensure that the problems it
solves are ones that really matter.  There's a lot of applied research out
there which never makes the translation to practice - and we don't intend to
add to it.

`For upcoming ideas, see our GitHub issue tracker <https://github.com/Zac-HD/hypofuzz/issues>`__.


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

.. literalinclude:: ../../../pyproject.toml
   :prepend: dependencies = [
   :start-after: dependencies = [
   :end-before: classifiers =


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
