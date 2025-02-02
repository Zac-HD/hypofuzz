import math
from typing import Optional

from hypothesis.internal.conjecture.choice import choice_permitted
from hypothesis.internal.conjecture.data import ConjectureData
from hypothesis.internal.conjecture.providers import (
    COLLECTION_DEFAULT_MAX_SIZE,
    PrimitiveProvider,
)
from hypothesis.internal.intervalsets import IntervalSet

from .corpus import ChoicesT


def fresh_choice(choice_type, kwargs, *, random):
    cd = ConjectureData(random=random)
    return getattr(cd.provider, f"draw_{choice_type}")(**kwargs)


class HypofuzzProvider(PrimitiveProvider):
    def __init__(
        self, conjecturedata: Optional[ConjectureData], /, *, choices: ChoicesT
    ):
        super().__init__(conjecturedata)
        self.choices = choices
        self.index = 0

    def _fresh_choice(self, choice_type, kwargs):
        return fresh_choice(choice_type, kwargs, random=self._cd._random)

    def _pop_choice(self, choice_type, kwargs):
        if self.index >= len(self.choices):
            # past our prefix. draw a random choice
            return self._fresh_choice(choice_type, kwargs)

        choice = self.choices[self.index]
        popped_choice_type = {
            int: "integer",
            float: "float",
            bool: "boolean",
            bytes: "bytes",
            str: "string",
        }[type(choice)]
        if choice_type != popped_choice_type or not choice_permitted(choice, kwargs):
            # misalignment. draw a random choice
            choice = self._fresh_choice(choice_type, kwargs)

        self.index += 1
        return choice

    def draw_boolean(
        self,
        p: float = 0.5,
    ) -> bool:
        return self._pop_choice("boolean", {"p": p})

    def draw_integer(
        self,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
        *,
        # weights are for choosing an element index from a bounded range
        weights: Optional[dict[int, float]] = None,
        shrink_towards: int = 0,
    ) -> int:
        return self._pop_choice(
            "integer",
            {
                "min_value": min_value,
                "max_value": max_value,
                "weights": weights,
                "shrink_towards": shrink_towards,
            },
        )

    def draw_float(
        self,
        *,
        min_value: float = -math.inf,
        max_value: float = math.inf,
        allow_nan: bool = True,
        smallest_nonzero_magnitude: float,
    ) -> float:
        return self._pop_choice(
            "float",
            {
                "min_value": min_value,
                "max_value": max_value,
                "allow_nan": allow_nan,
                "smallest_nonzero_magnitude": smallest_nonzero_magnitude,
            },
        )

    def draw_string(
        self,
        intervals: IntervalSet,
        *,
        min_size: int = 0,
        max_size: int = COLLECTION_DEFAULT_MAX_SIZE,
    ) -> str:
        return self._pop_choice(
            "string",
            {"intervals": intervals, "min_size": min_size, "max_size": max_size},
        )

    def draw_bytes(
        self,
        min_size: int = 0,
        max_size: int = COLLECTION_DEFAULT_MAX_SIZE,
    ) -> bytes:
        return self._pop_choice("bytes", {"min_size": min_size, "max_size": max_size})
