import math
from random import Random
from typing import Optional, cast

from hypothesis.internal.conjecture.choice import (
    ChoiceConstraintsT,
    ChoiceT,
    ChoiceTypeT,
    choice_permitted,
)
from hypothesis.internal.conjecture.data import ConjectureData
from hypothesis.internal.conjecture.providers import (
    COLLECTION_DEFAULT_MAX_SIZE,
    PrimitiveProvider,
)
from hypothesis.internal.intervalsets import IntervalSet

from hypofuzz.database import ChoicesT


def fresh_choice(
    choice_type: ChoiceTypeT, constraints: ChoiceConstraintsT, *, random: Random
) -> ChoiceT:
    cd = ConjectureData(random=random)
    choice = getattr(cd.provider, f"draw_{choice_type}")(**constraints)
    return cast(ChoiceT, choice)


class HypofuzzProvider(PrimitiveProvider):
    def __init__(
        self, conjecturedata: Optional[ConjectureData], /, *, choices: ChoicesT
    ) -> None:
        super().__init__(conjecturedata)
        self.choices = choices
        self.index = 0

    def _fresh_choice(
        self, choice_type: ChoiceTypeT, constraints: ChoiceConstraintsT
    ) -> ChoiceT:
        assert self._cd is not None
        assert self._cd._random is not None
        return fresh_choice(choice_type, constraints, random=self._cd._random)

    def _pop_choice(
        self, choice_type: ChoiceTypeT, constraints: ChoiceConstraintsT
    ) -> ChoiceT:
        if self.index >= len(self.choices):
            # past our prefix. draw a random choice
            return self._fresh_choice(choice_type, constraints)

        choice = self.choices[self.index]
        popped_choice_type = {
            int: "integer",
            float: "float",
            bool: "boolean",
            bytes: "bytes",
            str: "string",
        }[type(choice)]
        if choice_type != popped_choice_type or not choice_permitted(
            choice, constraints
        ):
            # misalignment. draw a random choice
            choice = self._fresh_choice(choice_type, constraints)

        self.index += 1
        return choice

    def draw_boolean(
        self,
        p: float = 0.5,
    ) -> bool:
        choice = self._pop_choice("boolean", {"p": p})
        assert isinstance(choice, bool)
        return choice

    def draw_integer(
        self,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
        *,
        # weights are for choosing an element index from a bounded range
        weights: Optional[dict[int, float]] = None,
        shrink_towards: int = 0,
    ) -> int:
        choice = self._pop_choice(
            "integer",
            {
                "min_value": min_value,
                "max_value": max_value,
                "weights": weights,
                "shrink_towards": shrink_towards,
            },
        )
        assert isinstance(choice, int)
        return choice

    def draw_float(
        self,
        *,
        min_value: float = -math.inf,
        max_value: float = math.inf,
        allow_nan: bool = True,
        smallest_nonzero_magnitude: float,
    ) -> float:
        choice = self._pop_choice(
            "float",
            {
                "min_value": min_value,
                "max_value": max_value,
                "allow_nan": allow_nan,
                "smallest_nonzero_magnitude": smallest_nonzero_magnitude,
            },
        )
        assert isinstance(choice, float)
        return choice

    def draw_string(
        self,
        intervals: IntervalSet,
        *,
        min_size: int = 0,
        max_size: int = COLLECTION_DEFAULT_MAX_SIZE,
    ) -> str:
        choice = self._pop_choice(
            "string",
            {"intervals": intervals, "min_size": min_size, "max_size": max_size},
        )
        assert isinstance(choice, str)
        return choice

    def draw_bytes(
        self,
        min_size: int = 0,
        max_size: int = COLLECTION_DEFAULT_MAX_SIZE,
    ) -> bytes:
        choice = self._pop_choice("bytes", {"min_size": min_size, "max_size": max_size})
        assert isinstance(choice, bytes)
        return choice
