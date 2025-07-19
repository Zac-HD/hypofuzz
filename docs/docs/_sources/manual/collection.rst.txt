Test collection
===============

Before HypoFuzz starts fuzzing by assigning tests to workers, it first needs to know what tests are available. HypoFuzz does so by running a collection step.

How HypoFuzz collects tests
---------------------------

HypoFuzz uses :pypi:`pytest` to collect test functions, with an almost identical command-line interface.

If you're using ``pytest ...`` to run your tests, ``hypothesis fuzz -- ...`` will fuzz them. Everything after ``--`` is passed to a call to ``pytest --collect-only`` in HypoFuzz.

Among others, this means you can use the standard pytest ``-k`` selector to configure which tests to run, with ``hypothesis fuzz -- -k ...``. See pytest's docs on :ref:`pytest:select-tests` and :ref:`pytest:test discovery` for more details.

Concretely, if your source layout looks like this:

.. code-block::

    src/
        ...
    tests/
        test_a.py
        test_b.py

and you normally run your tests with ``pytest``, then:

* ``hypothesis fuzz`` will fuzz all your tests
* ``hypothesis fuzz -- tests/test_a.py`` will fuzz the tests in ``test_a.py``
* ``hypothesis fuzz -- -k selector_string`` will fuzz the tests matching ``selector_string`` (see :ref:`pytest:select-tests`).

Pytest plugins during collection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``hypothesis fuzz`` does not run pytest plugins during collection. If your standard pytest command includes plugin parameters like ``pytest -n auto`` (from e.g. :pypi:`pytest-xdist`), do not pass these parameters to ``hypothesis fuzz``.


Skipping tests under HypoFuzz
-----------------------------

If you would like to skip a test under HypoFuzz while keeping it part of your normal test suite, you can use :ref:`pytest:pytest.mark.skipif ref` in combination with |in_hypofuzz_run|:

.. code-block:: python

    import pytest
    from hypothesis import given, strategies as st

    from hypofuzz.detection import in_hypofuzz_run


    @pytest.mark.skipif(in_hypofuzz_run)
    @given(st.integers())
    def test_will_not_be_fuzzed(n):
        pass

|in_hypofuzz_run| can also be used to mark tests which should run *only* under HypoFuzz, by inverting the conditional above.
