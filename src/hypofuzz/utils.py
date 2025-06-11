import heapq
import math
import threading
from collections.abc import Sequence
from enum import Enum
from typing import Any, Callable, Generic, Optional, TypeVar

from hypofuzz.compat import bisect_right

T = TypeVar("T")

FUZZJSON_INF = "hypofuzz-inf-a928fa52b3ea4a9a9af36ccef7c6cf93"
FUZZJSON_NINF = "hypofuzz-ninf-a928fa52b3ea4a9a9af36ccef7c6cf93"
FUZZJSON_NAN = "hypofuzz-nan-a928fa52b3ea4a9a9af36ccef7c6cf93"


def convert_to_fuzzjson(value: Any) -> Any:
    # converts a dict intended for json.dumps into "fuzzjson", which is json but
    # with ±math.inf and math.nan replaced by unique, stable strings, so the json
    # object can be parsed by JSON.parse in javascript instead of the slower
    # JSON5.parse.

    if isinstance(value, dict):
        return {key: convert_to_fuzzjson(value) for key, value in value.items()}
    elif isinstance(value, float):
        if value == math.inf:
            return FUZZJSON_INF
        elif value == -math.inf:
            return FUZZJSON_NINF
        elif math.isnan(value):
            return FUZZJSON_NAN
        return value
    elif isinstance(value, list):
        return [convert_to_fuzzjson(item) for item in value]
    elif isinstance(value, (bool, int, str, type(None))):
        return value
    elif isinstance(value, Enum):
        return convert_to_fuzzjson(value.value)
    else:
        raise ValueError(f"unknown type {type(value)} ({value!r})")


# hypothesis.utils.dynamicvariable, but without the with_value context manager.
# Essentially just a reference to a value.
class Value(Generic[T]):
    def __init__(self, default: T) -> None:
        self.default = default
        self.data = threading.local()

    @property
    def value(self) -> T:
        return getattr(self.data, "value", self.default)

    @value.setter
    def value(self, value: T) -> None:
        self.data.value = value


def lerp(a: float, b: float, t: float) -> float:
    return (1 - t) * a + t * b


def k_way_merge(
    lists: Sequence[Sequence[T]], key: Optional[Callable[[T], Any]] = None
) -> list[T]:
    # merges k sorted lists in O(nlg(k)) time, where n is the total number of
    # elements.
    #
    # NOTE: this implementation is *not* a stable sort, since the heap key
    #   (key(l[0]), i, 0)
    # falls back to i when key(l[0]) is equal.
    result: list[T] = []
    heap: list[tuple[Any, int, int]] = []
    lists = [l for l in lists if l]
    for i, l in enumerate(lists):
        heapq.heappush(heap, (key(l[0]) if key is not None else l[0], i, 0))

    while heap:
        _key, list_i, value_i = heapq.heappop(heap)
        val = lists[list_i][value_i]
        result.append(val)

        if value_i + 1 < len(lists[list_i]):
            next_value = lists[list_i][value_i + 1]
            heapq.heappush(
                heap,
                (
                    key(next_value) if key is not None else next_value,
                    list_i,
                    value_i + 1,
                ),
            )

    return result


def fast_bisect_right(
    a: Sequence[Any], x: Any, key: Optional[Callable[[Any], Any]] = None
) -> int:
    # this case isn't really for performance, but just to make the fast case checks
    # below easier.
    if len(a) == 0:
        return 0

    # Fast case for if x is at the end or the beginning of the list. Turns logn
    # into constant time.
    if x > (a[-1] if key is None else key(a[-1])):
        return len(a)
    if x < (a[0] if key is None else key(a[0])):
        return 0
    return bisect_right(a, x, key=key)
