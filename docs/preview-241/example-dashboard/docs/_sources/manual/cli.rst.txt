Command-line interface
======================

The ``hypothesis fuzz`` command is the main entrypoint to HypoFuzz. Installing HypoFuzz automatically adds the ``fuzz`` sub-command to the existing :ref:`Hypothesis CLI <hypothesis:hypothesis-cli>`.

``hypothesis fuzz``
-------------------

.. literalinclude:: ../cli_output_fuzz.txt
   :language: text

Example usage
~~~~~~~~~~~~~

* ``hypothesis fuzz`` starts the dashboard and fuzz workers, using all available cores.
* ``hypothesis fuzz -n 2`` starts the dashboard and fuzz workers, using 2 cores.
* ``hypothesis fuzz --dashboard-only`` starts just the dashboard. The dashboard works even if no fuzz workers are running.
* ``hypothesis fuzz --no-dashboard -n 4`` starts just the fuzz workers, using 4 cores.
* ``hypothesis fuzz -- -k parse`` starts the dashboard and fuzz workers only for test names with the string ``parse`` in them.
