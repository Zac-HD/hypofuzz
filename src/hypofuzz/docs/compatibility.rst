Compatibility
=============

HypoFuzz uses `calendar-based versioning <https://calver.org/>`__, with a
``YY-MM-patch`` format.

Because HypoFuzz is closely tied to Hypothesis internals, we recommend pinning
your transitive dependencies using a tool like :pypi:`pip-compile <pip-tools>`,
:pypi:`uv`, or :pypi:`pipenv`.  This makes it possible to reproduce old
environments based only on your version-control history, and ensures that any compatibility
problems in new releases can be handled when it suits you.

Pytest and unittest compatibility
---------------------------------

HypoFuzz is compatible with almost all features of Pytest and unittest. The features which are not are listed below. If any of these features are important to you, please `get in touch <mailto:sales@hypofuzz.com?subject=Test%20runner%20feature%20support>`__! They are not yet implemented in HypoFuzz due to low perceived use.

* Pytest's :ref:`xunit-style setup and teardown methods <pytest:xunitsetup>`. Like Pytest, we recommend using fixtures instead.

  * ``setup_module`` and ``teardown_module``
  * ``setup_class`` and ``teardown_class``
  * ``setup_method`` and ``teardown_method``
  * ``setup_function`` and ``teardown_function``

* Any unittest feature which is not supported by Pytest. Currently, this is only ``subTest`` and the ``load_tests`` protocol.


Direct dependencies
-------------------

HypoFuzz's direct dependencies are:

.. literalinclude:: ../../../pyproject.toml
   :prepend: dependencies = [
   :start-after: dependencies = [
   :end-before: classifiers =


API deprecation policy
----------------------

The command-line interface will not make incompatible changes without at least
three months notice, during which passing deprecated options will emit runtime
warnings (e.g. via the terminal, displayed on the dashboard, etc.).

User-accesible integration points with Hypothesis, such as the
:class:`~hypothesis:hypothesis.database.ExampleDatabase` API, are considered
stable upstream and are unlikely to change even in major version releases.

If it is impractical to continue to support old versions of Hypothesis (or other
dependencies) after a major update, the minimum supported version will be updated.
If you would like to use new versions of HypoFuzz with old versions of its
dependencies, please `get in touch <mailto:sales@hypofuzz.com?subject=Extended%20Hypothesis%20version%20support>`__ to discuss your specific needs.
