import sys
from itertools import islice
from random import Random

from hypothesis import strategies as st
from hypothesis.control import current_build_context
from hypothesis.errors import InvalidArgument
from hypothesis.internal.conjecture.choice import ChoiceNode
from hypothesis.internal.conjecture.data import ConjectureData
from hypothesis.internal.conjecture.provider_conformance import (
    choice_types_constraints,
    constraints_strategy,
)
from hypothesis.internal.intervalsets import IntervalSet

# most of this file is copied from relevant portions of the hypothesis testing code.
# it may fall out of date with improvements there.


def build_intervals(intervals):
    it = iter(intervals)
    while batch := tuple(islice(it, 2)):
        # To guarantee we return pairs of 2, drop the last batch if it's
        # unbalanced.
        # Dropping a random element if the list is odd would probably make for
        # a better distribution, but a task for another day.
        if len(batch) < 2:
            continue
        yield batch


def interval_lists(*, min_codepoint=0, max_codepoint=sys.maxunicode, min_size=0):
    return (
        st.lists(
            st.integers(min_codepoint, max_codepoint),
            unique=True,
            min_size=min_size * 2,
        )
        .map(sorted)
        .map(build_intervals)
    )


def intervals(*, min_codepoint=0, max_codepoint=sys.maxunicode, min_size=0):
    return st.builds(
        IntervalSet,
        interval_lists(
            min_codepoint=min_codepoint, max_codepoint=max_codepoint, min_size=min_size
        ),
    )


def fresh_data(*, random=None, observer=None) -> ConjectureData:
    if random is None:
        try:
            context = current_build_context()
        except InvalidArgument:
            # ensure usage of fresh_data() is not flaky outside of property tests.
            raise ValueError(
                "must pass a seeded Random instance to fresh_data() when "
                "outside of a build context"
            ) from None

        # within property tests, ensure fresh_data uses a controlled source of
        # randomness.
        # drawing this from the current build context is almost *too* magical. But
        # the alternative is an extra @given(st.randoms()) everywhere we use
        # fresh_data, so eh.

        # @example uses a zero-length data, which means we can't use a
        # hypothesis-backed random (which would entail drawing from the data).
        # In this case, use a deterministic Random(0).
        random = (
            context.data.draw(st.randoms(use_true_random=True))
            if (choices := context.data.max_choices) is None or choices > 0
            else Random(0)
        )

    return ConjectureData(random=random, observer=observer)


def clamped_shrink_towards(constraints):
    v = constraints["shrink_towards"]
    if constraints["min_value"] is not None:
        v = max(constraints["min_value"], v)
    if constraints["max_value"] is not None:
        v = min(constraints["max_value"], v)
    return v


def draw_value(choice_type, constraints):
    data = fresh_data()
    return getattr(data, f"draw_{choice_type}")(**constraints)


@st.composite
def choices(draw):
    (choice_type, constraints) = draw(choice_types_constraints())
    return draw_value(choice_type, constraints)


@st.composite
def nodes(draw, *, was_forced=None, choice_types=None):
    if choice_types is None:
        (choice_type, constraints) = draw(choice_types_constraints())
    else:
        choice_type = draw(st.sampled_from(choice_types))
        constraints = draw(constraints_strategy(choice_type))
    # choice nodes don't include forced in their constraints. see was_forced attribute
    del constraints["forced"]
    value = draw_value(choice_type, constraints)
    was_forced = draw(st.booleans()) if was_forced is None else was_forced

    return ChoiceNode(
        type=choice_type, value=value, constraints=constraints, was_forced=was_forced
    )
