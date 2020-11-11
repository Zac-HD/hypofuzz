# Meeting, 2020-11-03

Background: LibCST team; uses Hypothesis
Talking to Zsolt (@zsol on GH)


We have at least three inhouse fuzzers; not a direct hypothesis user


how would you use CI, fuzzing, etc.?

We have a very different take on CI to OSS for historical reasons
Tons of changes in monorepos, so batch and bisect on failure.
Run every remotely relevant test on each batch; only rerun failures on bisect
Plus integration-test-style fuzzers; not on PRs but on master and reset
hourly or daily.

As far as I'm aware but most of our backend in Python is not fuzzed (backend)
mostly fuzzing mobile or native code.
Partly not wanted for Python; partly too slow.
But if it's serious enough to need fuzzing, maybe just rewrite in another language

Can put me in touch with Thrift fuzzing team.

Internally, Hypothesis is rare - mostly on OSS projects where someone else has contributed



Internally it's mostly unittest, some pytest.  Also internal "testslide" framework.
Also a service-isolation framework.



What's useful or frustrating in a fuzzer?

It's something that runs in the background; tells me about things unit tests have
missed.  Don't really care about speed, so long as it's not blocking workflow.
Once issue found; let me dig into it quickly (less than minutes)

Plus: ease of setup is usually painful.  Hypothesis isn't always trivial to set up
in a *useful* way - as in, testing nontrivial or otherwise untested properties.
E.g. couldn't set up for Black in a few days - source code is hard.
