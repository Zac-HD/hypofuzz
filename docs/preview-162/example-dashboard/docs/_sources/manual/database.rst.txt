HypoFuzz database
=================

The HypoFuzz database stores all the persistent information necessary for fuzzing, including the covering corpus of inputs, any failures found, and progress of behaviors discovered over time.

The HypoFuzz database is a standard :ref:`Hypothesis database <hypothesis:database>`.

Configure which database HypoFuzz uses
--------------------------------------

HypoFuzz determines which database to use as follows:

* Run a pytest test collection step.
* Then, use the :obj:`.database <hypothesis:hypothesis.settings.database>` attribute of the current :obj:`settings profile <hypothesis:hypothesis.settings>`.

To configure which database HypoFuzz uses, register and load a Hypothesis settings profile with the desired database. So for instance, to tell HypoFuzz to use a redis database, place the following in any module loaded during pytest's test collection:

.. code-block:: python

    from hypothesis import settings

    # pip install hypothesis[redis]
    from hypothesis.extra.redis import RedisExampleDatabase

    db = RedisExampleDatabase(redis=...)
    settings.register_profile("custom_db", database=db)
    settings.load_profile("custom_db")

In practice, this code is usually placed in the ``__init__.py`` file of the test module (such as ``tests/__init__.py``). If using pytest, an alternative standard place for this code is in a ``conftest.py`` file (such as ``tests/conftest.py``).

How HypoFuzz uses the database
------------------------------

HypoFuzz is split into two components: the dashboard (``--dashboard-only``), and the fuzz workers (``--no-dashboard``). The dashboard process requires a read view of the database, while the fuzz workers requires a read-write view of the database.

The dashboard and the fuzz workers should use the same database. If they do not, the dashboard will not be able to show progress and/or failures from the fuzz workers. If you are launching fuzz workers independently of the dashboard, ensure that both read and write to the same database (for instance, making sure that no environment variables cause a different database to be selected for the dashboard and the fuzz workers).

When HypoFuzz finds a failure, it writes it to the standard location in the Hypothesis database. This lets Hypothesis replay the failure even when you run your tests without HypoFuzz. It's therefore critical that the fuzzer is using the *same* database as Hypothesis, regardless of how or where you run it.

Writing your own database
-------------------------

The HypoFuzz database is a standard :ref:`hypothesis database <hypothesis:database>`, which is a simple key-value store that maps bytestrings to lists of bytestrings. Writing your own database requires implementing only the ``.fetch(key: bytes)``, ``.save(key: bytes, value: bytes)``, and ``.delete(key: bytes, value: bytes)`` methods. See the Hypothesis :doc:`hypothesis:how-to/custom-database` how-to for more details.

.. note::

    We've already sketched designs for Hypothesis databases backed by S3, DynamoDB, and other cloud storage solutions. If something in this space would be useful for you, please `get in touch <mailto:sales@hypofuzz.com?subject=HypoFuzz%20database%20support>`__ and we can bump it up our todo list!

Once you've written your own database, you can tell HypoFuzz to use it like any other database:

.. code-block:: python

    from hypothesis import settings
    from hypothesis.database import ExampleDatabase


    class MyDatabase(ExampleDatabase):
        def fetch(self, key: bytes):
            pass

        def save(self, key: bytes, value: bytes):
            pass

        def delete(self, key: bytes, value: bytes):
            pass


    db = MyDatabase()
    settings.register_profile("custom_db", database=db)
    settings.load_profile("custom_db")
