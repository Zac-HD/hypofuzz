Test collection
===============

HypoFuzz uses :pypi:`pytest` to collect the test functions to fuzz, with almost identical command-line interfaces.  If you're using ``pytest ...`` to run your tests, ``hypothesis fuzz -- ...`` will fuzz them.

This also means you can use the standard pytest ``-k`` selector to configure which tests to run, with ``hypothesis fuzz -- -k ...``. See pytest's docs on :ref:`pytest:select-tests` and :ref:`pytest:test discovery` for more details.

Note that tests which use `pytest fixtures <https://docs.pytest.org/en/stable/fixture.html>`__ are not collected, as they may behave differently outside of the pytest runtime. We recommend using a context manager and the ``with`` statement instead. Support for pytest fixtures is on :doc:`our roadmap </roadmap>`.

Support for other test runners, such as :mod:`python:unittest`, is on our roadmap.

Skipping tests under HypoFuzz
-----------------------------

If you would like to skip a test under HypoFuzz while keeping it part of your normal test suite, you can use |in_hypofuzz_run|:

.. code-block:: python

    import pytest
    from hypothesis import given, strategies as st

    from hypofuzz.detection import in_hypofuzz_run


    @pytest.mark.skipif(in_hypofuzz_run)
    @given(st.integers())
    def test_will_not_be_fuzzed(n):
        pass

You can also use |in_hypofuzz_run| to run certain tests *only* under HypoFuzz.
