import os

# If this envvar is set, Hypothesis loads the CI profile. We can't combine that
# with hypofuzz, since the CI profile sets derandomize=True, which hypofuzz
# skips during collection.
#
# This has to be changed at the os.environ level, instead of doing
# settings.load_profile("default"), because pytest collection and subprocesses
# inherit the current os.environ and would think themselves as in CI.
os.environ.pop("__TOX_ENVIRONMENT_VARIABLE_ORIGINAL_CI", None)
