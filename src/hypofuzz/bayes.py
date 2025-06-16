import math
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hypofuzz.hypofuzz import FuzzTarget


def distribute_nodes(
    nodeids: Sequence[str], estimators: Sequence[float], *, n: int
) -> tuple[tuple[str, ...], ...]:
    # We have x nodes node_i, each with an estimator \hat{v}_i for "behaviors per
    # second". We have n bins (processes), and we want to distribute node_i
    # into the n bins such that we maximize overall behaviors per second.
    #
    # If our estimators \hat{v}_i were static, then this is trivial: the
    # overall behaviors per second is `sum from i=1 to c of max(p_i)`. Of course,
    # our estimators are *not* static. Which means we are optimizing over something
    # more complicated - a set of multi-armed bandit problems perhaps?
    #
    # A more naive quantity to maximize (minimize) is the largest bin sum.
    # So we are minimizing `max(sum(p_i) for i in c)`. This is related to
    # "makespan minimization", and is a classic bin packing problem. Optimality
    # is NP complete, so we approximate the optimal solution with a greedy one,
    # specifically "longest processing time first scheduling".
    #
    # (intuitively, we assign the "best" nodes to processes first. So with
    # e.g. 10 nodes with an estimator of \hat{v}_i = 1 behavior per second (which
    # is really good!) they would all go to different processes (at least until
    # the cap of n processes), which is what we want.

    assert len(nodeids) == len(estimators)
    # estimators of 0 are mathematically valid, but semantically weird, and much
    # more likely to be indicative of a logic error
    assert all(estimator > 0 for estimator in estimators)

    bins: list[list[Any]] = [[] for _ in range(n)]
    nodes = [
        {"nodeid": nodeid, "estimator": estimator}
        for nodeid, estimator in zip(nodeids, estimators)
    ]

    # first, we sort the node_i in decreasing order by their estimator.
    nodes.sort(key=lambda node: node["estimator"], reverse=True)  # type: ignore

    # If we have fewer than `n` nodes, we repeat the list of nodes in decreasing
    # order of their estimator until we reach `n` nodes. This ensures every
    # processes receives a node (in fact, in this case, exactly one).
    node_idx = 0
    while len(nodes) < n:
        nodes.append(nodes[node_idx])
        node_idx = (node_idx + 1) % len(nodes)

    # then, we assign each node_i to the partition with the least sum.
    for node in nodes:
        smallest_bin = min(
            bins,
            key=lambda bin: sum(node["estimator"] for node in bin),
        )
        smallest_bin.append(node)

    return tuple(tuple(node["nodeid"] for node in bin) for bin in bins)


# for the behaviors estimators, we should incorporate a lookback across the
# history of workers for this test. Give higher weight to newer estimators
# (proportional to their confidence ie sample size).


def behaviors_per_input(target: "FuzzTarget") -> float:
    # an estimator for the number of behaviors the next input will discover.
    since = target.provider.since_new_branch
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
