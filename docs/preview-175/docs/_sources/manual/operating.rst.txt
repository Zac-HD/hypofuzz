Operating HypoFuzz
==================

HypoFuzz makes it easy to get started (or keep going!) on your laptop. We also support scaling up to a shared server for team-size projects, and then scaling out across multiple servers, or spot instances and idle capacity as they come and go.

This page has configuration tips for each of those environments, including how to reproduce failing examples with Hypothesis for debugging if the dashboard wasn't enough.

Running on your laptop
----------------------

For running HypoFuzz locally on your laptop, we recommend simply using ``hypothesis fuzz``, which launches both the dashboard and the associated fuzz workers.

If you like, you can run ``hypothesis fuzz --dashboard-only`` and ``hypothesis fuzz --no-dashboard`` as separate commands, so you can stop the fuzz workers while still being able to view the dashboard. You can launch the dashboard at any time with ``hypothesis fuzz --dashboard-only``, whether or not any fuzz workers are running.

The dashboard's "Collection" page shows which tests were collected (or not collected) by HypoFuzz, which may be helpful for debugging.

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

As with the single-server case, we recommend running a permanent dashboard with ``hypothesis fuzz --dashboard-only``, and running ``hypothesis fuzz --no-dashboard`` on each distributed worker.

Starting a fuzz process with hypothesis fuzz has a moderate startup cost before it begins to do useful work. It has to complete pytest collection (typically a few seconds), and then replay any covering inputs discovered by previous runs in order to reload state. Improving the cost/benefit ratio of short runs, by spreading the replay cost over a longer period, is on our roadmap.

Additionally, HypoFuzz's adaptive techniques make compute allocation more efficient over the lifetime of a worker process. While short runs already do useful work, and we aim to improve the ratio by persisting estimator states, the sixtieth minute is likely to be several times more valuable than the first.

Unless you're testing interactively or using noticeably cheaper spot instances, we recommend running HypoFuzz at least "over lunch", and more typically "overnight" - restarting every 12 or 24 hours to pick up code changes.

As for the database on a distributed system, we recommend using Redis with :class:`~hypothesis:hypothesis.extra.redis.RedisExampleDatabase`. Alternatively, you can easily write your own database class (see :doc:`/manual/database`), and contributions of database class implementations to Hypothesis are most welcome as well!
