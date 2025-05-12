Custom coverage events
======================

HypoFuzz collects branch coverage of your code on every input. However, we know that there are many things code can do that aren't captured by
the set of executed branches.  `This blog post
<https://blog.foretellix.com/2016/12/23/verification-coverage-and-maximization-the-big-picture/>`__
gives a good overview of coverage-driven verification workflows.

We therefore treat each :func:`hypothesis.event` as a "virtual" branch - while it's
not part of the control-flow graph, we keep track of inputs which produced each
observed event in the same way that we track the inputs which produce each branch.

You can therefore use the :func:`~hypothesis.event` function in your tests to
mark out categories of behaviour, boundary conditions, and so on, and then let the
fuzzer exploit that to generate more diverse and better-targeted inputs.
And as a bonus, you'll get useful summary statistics when running Hypothesis!
