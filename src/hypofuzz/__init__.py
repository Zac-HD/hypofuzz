"""Adaptive fuzzing for property-based tests using Hypothesis."""

from .hy import coverage_fuzzer, fuzz_in_generator

__version__ = "0.0.1"
__all__ = ["coverage_fuzzer", "fuzz_in_generator"]
