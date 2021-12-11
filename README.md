# [HypoFuzz](https://hypofuzz.com/)

*Adaptive fuzzing of [Hypothesis](https://hypothesis.readthedocs.io) tests.*


Property-based approaches help you to write better tests which find more bugs,
but don't have great ways to exchange much more CPU time for more bugs.
The goal of this project is to bring togther the best parts of fuzzing and PBT.


## Motivation

You can [run a traditional fuzzer](https://hypothesis.readthedocs.io/en/latest/details.html#use-with-external-fuzzers)
like AFL on Hypothesis tests to get basic coverage guidance.

- This does actually work, which is pretty cool
- It's very slow though, and often fails to parse the bytes into an example
- Installing, configuring, and connecting all the parts is a pain
- Also assumes one fuzz target per core, which doesn't scale very far

Alternatively, you can just run Hypothesis with a large `max_examples` setting.
This also works pretty well, but doesn't get the benefits of coverage guidance
(i.e. avoiding the exponential scaling cliff by learning from feedback) and
also occupies one fuzz target per core.

(turns out that you can [emulate coverage guidance](https://engineering.backtrace.io/posts/2020-03-11-how-hard-is-it-to-guide-test-case-generators-with-branch-coverage-feedback/)
with `hypothesis.target()`, which appears to work well enough as a starting point)

(also Hypothesis used to have coverage guidance built in, but we took it back out
because of performance and ecosystem integration problems - as a rule of thumb it's
just not worth the trouble for less than a thousand inputs.
[see here](https://github.com/HypothesisWorks/hypothesis/pulls?q=is%3Amerged+use_coverage).)


## Features

- Interleave execution of many test functions
- Prioritise functions where we expect to make progress
- Coverage-guided exploration of your system-under-test
- Seamless python-native and CLI integrations
- Web-based time-travel debugging with [PyTrace](https://pytrace.com/)
  (automatic if you `pip install hypofuzz[pytrace]`)


## Changelog

Patch notes [can be found in `CHANGELOG.md`](https://github.com/Zac-HD/hypofuzz/blob/master/CHANGELOG.md).


## License

This is an active research project as part of my (Zac Hatfield-Dodds) PhD.

Unlike Hypothesis, it is *not* open source and I am not seeking external contributions.

As a complement to users of free, world-class PBT tools, I'm planning to sell
licenses in order to fund ongoing work on both this project and Hypothesis itself.
Please [contact me](mailto:sales@hypofuzz.com) if you are interested.
