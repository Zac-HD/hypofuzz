Quickstart
==========

This page will get you set up using HypoFuzz.

Prerequisite: Have some Hypothesis tests
----------------------------------------

HypoFuzz runs :pypi:`hypothesis` tests, so you'll need some of those first. If you don't have any Hypothesis tests yet, check out the :doc:`Hypothesis quickstart guide <hypothesis:quickstart>`, then come back after writing some!

Installation
------------

HypoFuzz is a pure python package, and can be installed with:

.. code-block:: shell

    pip install hypofuzz

Running HypoFuzz
----------------

The main entrypoint to HypoFuzz is ``hypothesis fuzz``. This sub-command of the :ref:`hypothesis command line <hypothesis:hypothesis-cli>` is automatically created when installing HypoFuzz.

The no-argument command ``hypothesis fuzz`` does two things:

* Starts a local dashboard webserver, and
* Executes your Hypothesis tests using all available cores

These behaviors can be isolated with the ``--dashboard-only`` and ``--no-dashboard`` commands respectively, and the number of cores used can be controlled with ``-n/--num-processes``.

HypoFuzz uses :pypi:`pytest` to collect available tests. ``hypothesis fuzz`` should therefore be run in a directory where pytest can discover your tests.

Any arguments after ``hypothesis fuzz --`` are passed through to pytest. See :doc:`/manual/collection` for how to use this to configure which tests are collected.

.. note::

    See the :doc:`command-line interface </manual/cli>` user manual for a full reference.

Running on your laptop
----------------------

For running HypoFuzz locally on your laptop, we recommend simply using ``hypothesis fuzz``, which launches both the dashboard and the associated fuzz workers.

If you like, you can run ``hypothesis fuzz --dashboard-only`` and ``hypothesis fuzz --no-dashboard`` as separate concurrent commands, so you can stop the fuzz workers while still being able to view the dashboard.

Running on a server
-------------------

This section is for running HypoFuzz on a single, centralized server.

We recommend running a permanent dashboard with ``hypothesis fuzz --dashboard-only``, and launching separate fuzz workers with ``hypothesis fuzz --no-dashboard`` whenever appropriate. (This might be "after every commit, for an hour", or "once a day for an hour", or on a manual trigger). You can of course combine both with ``hypothesis fuzz`` if you want to configure your server to search for bugs indefinitely.

Reproducing failures locally
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Since HypoFuzz is running on a server, developers will need to connect to the server's Hypothesis database in order to locally reproduce failures found by HypoFuzz.

The details of configuring this depends on your network topology. For instance, if you have a shared filesystem with the server, you can simply configure your database as a :class:`~hypothesis:hypothesis.database.DirectoryBasedExampleDatabase` pointed to the location of the ``.hypothesis`` database on the server. In more complex cases, you may need to use a networked database such as :class:`~hypothesis:hypothesis.extra.redis.RedisExampleDatabase`, or write your own database class.

.. note::

    See :doc:`/manual/database` for details on the HypoFuzz database, and how to write your own database class.

In the worst case (and if the server is using :class:`~hypothesis:hypothesis.database.DirectoryBasedExampleDatabase`), you can copy the ``.hypothesis`` directory on the server to your local copy of the codebase to reproduce failures.

Running on a distributed system
-------------------------------

This section is for running HypoFuzz on a distributed system, where distributed workers might come and go, with varying degrees of compute load.

As with the single-server case, we recommend running a permanent dashboard with ``hypothesis fuzz --dashboard-only``, and running ``hypothesis fuzz --no-dashboard`` on each distributed worker. Starting a fuzz process with ``hypothesis fuzz`` has some amount of overhead before it starts to be effective, so the longer each distributed worker lives, the better.

.. note::

    We plan to reduce the per-worker overhead in the future.

For the database on a distributed system, we recommend using Redis with :class:`~hypothesis:hypothesis.extra.redis.RedisExampleDatabase`. Alternatively, you can easily write your own database class (see :doc:`/manual/database`), and contributions of database class implementations to Hypothesis are most welcome as well!
