Custom coverage events
======================

HypoFuzz collects branch coverage of your code on every input. However, we know that there are many things code can do that aren't captured by
the set of executed branches.

We therefore treat the :func:`hypothesis.event` function as a "virtual" branch. While not
part of the control-flow graph, we treat inputs which produce a new event the same
as inputs which execute a new branch.

You can take advantage of this by using :func:`hypothesis.event` to guide HypoFuzz towards
interesting parts of your code. This might include categories of behavior, boundary conditions, etc; particularly those which are not already represented by a branch in your code. HypoFuzz will direct its fuzzing efforts towards these areas. (And as a bonus, you'll get :ref:`summary statistics <hypothesis:statistics>` about the events when running Hypothesis!)

For example, if you are testing a url parser, you might consider strings with multiple domains to be a particularly interesting case. You can give HypoFuzz a virtual branch in this case with :func:`hypothesis.event`:

.. code-block:: python

    from hypothesis import event, given, strategies as st


    @given(st.urls())
    def test_parse_url(url: str):
        if len(url.split(".")) > 2:
            event("multiple_domains")

        parse_url(url)

(Though if ``parse_url`` already has a branch for the multiple-domain case, then adding a virtual branch like this is unlikely to help.)

Finally, `this blog post
<https://blog.foretellix.com/2016/12/23/verification-coverage-and-maximization-the-big-picture/>`__
gives a good overview of this coverage-driven verification workflow.
