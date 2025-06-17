import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hypofuzz.hypofuzz import FuzzTarget

# for the behaviors estimators, we should incorporate a lookback across the
# history of workers for this test. Give higher weight to newer estimators
# (proportional to their confidence ie sample size).


def behaviors_per_input(target: "FuzzTarget") -> float:
    # an estimator for the number of behaviors the next input will discover.
    since = target.provider.since_new_behavior
    return (1 / since) if since > 0 else 1


def behaviors_per_second(target: "FuzzTarget") -> float:
    # an estimator for the number of behaviors discovered per second, assuming
    # one process is fuzzing this target continuously over that second.
    # This is a simple adjustment of behaviors_per_input for the test runtime.
    ninputs = target.provider.ninputs
    elapsed_time = target.provider.elapsed_time

    if elapsed_time == 0:
        return 1

    inputs_per_second = ninputs / elapsed_time
    return behaviors_per_input(target) * inputs_per_second


def softmax(values: list[float]) -> list[float]:
    if not values:
        return []
    # subtract max for numerical stability
    max_value = max(values)
    softmaxed = [math.exp(value - max_value) for value in values]

    total = sum(softmaxed)
    return [value / total for value in softmaxed]
