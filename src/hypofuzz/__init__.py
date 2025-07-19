"""Adaptive fuzzing for property-based tests using Hypothesis."""

from hypofuzz.detection import in_hypofuzz_run

__version__ = "25.07.01"
__all__: list[str] = ["in_hypofuzz_run"]
