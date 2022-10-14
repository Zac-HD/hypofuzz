# [HypoFuzz](https://hypofuzz.com/)

*Adaptive fuzzing of [Hypothesis](https://hypothesis.readthedocs.io) tests.*


Property-based approaches help you to write better tests which find more bugs,
but don't have great ways to exchange much more CPU time for more bugs.
The goal of this project is to bring togther the best parts of fuzzing and PBT.


## Motivation

You can [run a traditional fuzzer](https://hypothesis.readthedocs.io/en/latest/details.html#use-with-external-fuzzers)
like AFL on Hypothesis tests to get basic coverage guidance.  This works OK, but there's
a lot of performance overhead.  Installing, configuring, and connecting all the parts is
a pain, and because it assumes one fuzz target per core you probably can't scale up far
enough to fuzz your whole test suite.

Alternatively, you can just run Hypothesis with a large `max_examples` setting.
This also works pretty well, but doesn't get the benefits of coverage guidance and
you have to guess how long it'll take to run the tests - each gets the same budget.

HypoFuzz solves all of these problems, and more!


## Features

- Interleave execution of many test functions
- Prioritise functions where we expect to make progress
- Coverage-guided exploration of your system-under-test
- Seamless python-native and CLI integrations (replaces the `pytest` command)
- Web-based time-travel debugging with [PyTrace](https://pytrace.com/)
  (automatic if you `pip install hypofuzz[pytrace]`)

Read more about HypoFuzz at https://hypofuzz.com/docs/, including
[the changelog](https://hypofuzz.com/docs/changelog.html).
