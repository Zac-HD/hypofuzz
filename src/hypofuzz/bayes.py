import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import takewhile
from random import Random
from typing import TYPE_CHECKING, Any, Optional, TypeVar

if TYPE_CHECKING:
    from hypofuzz.hypofuzz import FuzzTarget

T = TypeVar("T")

# in the absence of any knowledge about worker lifetimes, assume a worker lives
# for 5 minutes.
DEFAULT_EXPECTED_LIFETIME_ESTIMATOR = 60 * 5


@dataclass
class CurrentWorker:
    nodeids: Sequence[str]
    e_lifetime: float


@dataclass
class DistributeNodesTarget:
    nodeid: str
    rates: "BehaviorRates"
    e_startup_time: float


@dataclass
class BehaviorRates:
    # An estimator for the number of behaviors the next input will discover. This
    # will be between 0 and 1.
    per_input: float
    # An estimator for the number of behaviors discovered per second for a target,
    # assuming one worker is fuzzing this target continuously over that second.
    per_second: float


def _min_values(values: Sequence[T], key: Any) -> Sequence[T]:
    candidates = sorted(
        [(value, key(value)) for value in values], key=lambda item: item[1]
    )
    min_value = candidates[0][1]
    return [
        item[0] for item in takewhile(lambda item: item[1] == min_value, candidates)
    ]


def distribute_nodes(
    targets: Sequence[DistributeNodesTarget],
    *,
    n: int,
    current_workers: Optional[Sequence[CurrentWorker]] = None,
) -> tuple[tuple[str, ...], ...]:
    # We have x nodes node_i, each with an estimator \hat{v}_i for "behaviors per
    # second". We have n bins (worker), and we want to distribute node_i
    # into the n bins such that we maximize the the sum of worker_behaviors.
    #
    # The estimator for the number of behaviors for a worker is given by
    # e_worker_behaviors. Instead of trying for the optimal solution of maximizing
    # the sum of worker_behaviors, we instead maximize the smallest worker_behaviors
    # quantity.
    #
    # This is related to "makespan minimization", and is a classic bin packing
    # problem. Optimality of this problem is NP complete, so we instead approximate
    # the optimal solution with a greedy one, specifically a variant of
    # "longest processing time first scheduling": we first sort the nodes in
    # increasing order of their estimator. Then, for each mode, we check which
    # worker has the lowest worker_behaviors, and assign the node to that worker.
    # Since we are iterating in increasing order of estimator, we know that adding
    # a node to a worker will increase that worker's worker_behaviors (unless the
    # worker's scheduling algorithm for targets is literally adversarial, ie
    # adding a higher-than-average value target decreases its expected behaviors
    # per second, which we will assume is not the case).
    #
    # Optionally, the current assignment `current_workers` of node ids to workers
    # can be passed. This incorporates an overhead cost to switching a nodeid to a
    # different worker. The algorithm is the standard bin packing algorithm, but
    # with a penalty to a node being assigned to a worker other than its current
    # worker.
    #
    # This penalty cost of switching a nodeid between workers is
    # worker_behaviors_per_second * node_startup_cost_seconds, ie the number of
    # behaviors we expect to lose by spending time starting up this node. We
    # only switch a nodeid between workers if the expected gain of doing so is
    # greater than this penalty. Note that in practice the penalty is applied
    # during assignment of nodes to workers in the greedy algorithm, so the penalty
    # may not produce optimal results, since the greedy solution is only an
    # approximation in general.

    random = Random()
    if current_workers is None:
        current_workers = [CurrentWorker(nodeids=[], e_lifetime=0.0) for _ in range(n)]

    assert len(current_workers) == n

    # estimators of 0 are mathematically valid, but can lead to bad/pathological
    # algorithm outcomes
    assert all(target.rates.per_second > 0 for target in targets)
    assert all(target.rates.per_input > 0 for target in targets)

    # return partitions in the same iteration order they were passed in current_workers
    workers: list[dict[str, Any]] = [
        {"current_worker": worker, "targets": []} for worker in current_workers
    ]

    # first, we sort the target in increasing order by their estimator.
    targets = sorted(targets, key=lambda target: target.rates.per_second)

    # If we have fewer than `n` targets, we repeat the list of targets in decreasing
    # order of their estimator until we reach `n` targets. This ensures every
    # worker receives at least one target (in fact, in this case, exactly one).
    target_idx = 0
    while len(targets) < n:
        # `targets` are in increasing order, so we index negatively to get
        # a decreasing order
        targets.append(targets[-target_idx])
        target_idx = (target_idx + 1) % len(targets)

    # then, we assign each target to the worker with the lowest worker_behaviors.
    # Since we're iterating over the targets in increasing order of behaviors
    # per-second, adding a target to a worker will always increase its
    # worker_behaviors.
    def worker_score(
        worker: dict[str, Any], *, target: Optional[DistributeNodesTarget] = None
    ) -> float:
        e_lifetime: float = worker["current_worker"].e_lifetime
        worker_rates = e_worker_rates(
            target_rates=[target.rates for target in worker["targets"]],
        )
        offset = 0.0
        if target is not None and target.nodeid not in worker["current_worker"].nodeids:
            # Add a penalty for switching nodes between workers. Since the ordering
            # quantity is the e_worker_behaviors estimator of lifetime worker
            # behaviors, we want to allow a node to switch workers if the ev
            # differential is greater than the number of behaviors we expect to
            # lose from spending time starting up this worker.
            #
            # And the number of behaviors we expect to lose is the behaviors per
            # second estimator for the worker, times the estimator for the startup
            # time of this node.
            #
            # We are choosing the worker with the lowest score to add this node to,
            # so if we want to encourage this node to be assigned to its current
            # worker, we want that worker to have a low score, which means we
            # want to increase the score of all other workers. So the offset here
            # should be positive.
            offset = worker_rates.per_second * target.e_startup_time
            assert offset >= 0, offset

        # to avoid crazy rebalancing during the initial startup phase, don't
        # work with small lifetime estimators
        e_lifetime = max(e_lifetime, DEFAULT_EXPECTED_LIFETIME_ESTIMATOR)
        return e_worker_behaviors(rates=worker_rates, e_lifetime=e_lifetime) + offset

    for target in targets:
        # find all the workers with the minimum value score, and randomly assign
        # this target to one of them. Normally there won't be ties, and the target
        # simply goes to the lowest worker. But when fuzzing for the first time
        # (or after a db wipe) where all targets have the same estimators, we
        # don't want to end in an assignment where one worker is given n - 1 nodes
        # and the other is given just 1.
        smallest_workers = _min_values(
            workers,
            key=lambda worker: worker_score(worker, target=target),
        )
        smallest_worker = random.choice(smallest_workers)

        score_before = worker_score(smallest_worker)
        smallest_worker["targets"].append(target)
        # ignore float rounding errors for our invariant check
        assert worker_score(smallest_worker) - score_before >= -1e-6, (
            score_before,
            worker_score(smallest_worker),
        )

    return tuple(
        tuple(target.nodeid for target in worker["targets"]) for worker in workers
    )


# TODO for the behaviors estimators, we should incorporate a lookback across the
# history of workers for this test. Give higher weight to newer estimators
# (proportional to their confidence ie sample size).


def e_target_rates(target: "FuzzTarget") -> BehaviorRates:
    # per_input computation
    since = target.provider.since_new_behavior
    per_input = (1 / since) if since > 0 else 1

    # per_second computation
    ninputs = target.provider.ninputs
    elapsed_time = target.provider.elapsed_time

    if elapsed_time == 0:
        per_second = 1.0
    else:
        inputs_per_second = ninputs / elapsed_time
        per_second = per_input * inputs_per_second

    return BehaviorRates(per_input=per_input, per_second=per_second)


def e_worker_lifetime(current_lifetime: float) -> float:
    """
    An estimator for the total lifetime of a worker.
    """
    # We use the doomsday-argument estimator that the total lifetime is twice the
    # current lifetime. In the future, this could incorporate past worker
    # lifetimes as well.
    return current_lifetime * 2


def e_worker_behaviors(rates: BehaviorRates, e_lifetime: float) -> float:
    """
    An estimator for the total number of behaviors we expect a worker to discover
    over its lifetime.

    `lifetime` is the estimator for the worker's total lifetime, given by
    e_worker_lifetime.
    """
    return rates.per_second * e_lifetime


def e_worker_rates(*, target_rates: Sequence[BehaviorRates]) -> BehaviorRates:
    # the expected behavior rates of a worker is
    # sum(probability * expected_value) for each of its targets.
    #
    # Note that this estimator is tightly dependent on the sampling algorithm used
    # in practice by the workers. If that changes (to e.g. thompson sampling), this
    # estimator will need to change to use the same sampling algorithm as well.
    # (ie, both places need to continue calling the same bandit_weights function).
    weights = bandit_weights(target_rates)
    return BehaviorRates(
        per_input=sum(p * rates.per_input for p, rates in zip(weights, target_rates)),
        per_second=sum(p * rates.per_second for p, rates in zip(weights, target_rates)),
    )


def softmax(values: list[float]) -> list[float]:
    if not values:
        return []
    # subtract max for numerical stability
    max_value = max(values)
    softmaxed = [math.exp(value - max_value) for value in values]

    total = sum(softmaxed)
    return [value / total for value in softmaxed]


def bandit_weights(behavior_rates: Sequence[BehaviorRates]) -> list[float]:
    """
    Returns the probability that each target should be chosen, as a solution
    to the multi-armed-bandit problem.
    """

    # choose the next target to fuzz with probability equal to the softmax
    # of its expected value (behaviors per second), aka boltzmann exploration
    per_second_estimators = [rates.per_second for rates in behavior_rates]
    return softmax(per_second_estimators)
