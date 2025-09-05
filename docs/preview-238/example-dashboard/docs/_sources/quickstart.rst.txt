Quickstart
==========

This quickstart will get you set up using HypoFuzz.

Prerequisite: Have some Hypothesis tests
----------------------------------------

HypoFuzz runs :pypi:`hypothesis` tests, so you'll need some of those first. If you don't have any Hypothesis tests yet, check out the :doc:`Hypothesis quickstart guide <hypothesis:quickstart>`, go write some Hypothesis tests, then come back!

Installation
------------

HypoFuzz is a pure python package, and can be installed with:

.. code-block:: shell

    pip install hypofuzz

Running HypoFuzz
----------------

The main entrypoint to HypoFuzz is ``hypothesis fuzz``. Installing HypoFuzz automatically adds this ``fuzz`` sub-command to the existing :ref:`Hypothesis CLI <hypothesis:hypothesis-cli>`.

The no-argument command ``hypothesis fuzz`` does two things:

* Starts a local dashboard webserver, and
* Executes your Hypothesis tests using all available cores

These behaviors can be isolated with the ``--dashboard-only`` and ``--no-dashboard`` commands respectively. The number of cores used can be controlled with ``-n/--num-processes``.

HypoFuzz uses :pypi:`pytest` to collect available tests. ``hypothesis fuzz`` should therefore be run in a directory where pytest can discover your tests.

Any arguments after ``hypothesis fuzz --`` are passed through to pytest. See :doc:`/manual/collection` for how to use this to control which tests are collected.

.. seealso::

    See the :doc:`command-line interface </manual/cli>` docs for a full command reference, and the :doc:`operating guide </manual/operating>` for advice on configuring HypoFuzz.
