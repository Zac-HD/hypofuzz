import math
import threading
from typing import Any, Generic, TypeVar

FUZZJSON_INF = "hypofuzz-inf-a928fa52b3ea4a9a9af36ccef7c6cf93"
FUZZJSON_NINF = "hypofuzz-ninf-a928fa52b3ea4a9a9af36ccef7c6cf93"
FUZZJSON_NAN = "hypofuzz-nan-a928fa52b3ea4a9a9af36ccef7c6cf93"

T = TypeVar("T")


def convert_to_fuzzjson(value: Any) -> Any:
    # converts a dict from e.g. json.dumps into "fuzzjson", which is json but
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
    else:
        raise ValueError(f"unknown type {type(value)} ({value!r})")


def lerp(a: float, b: float, t: float) -> float:
    return (1 - t) * a + t * b


# hypothesis.utils.dynamicvaraible, but without the with_value context manager.
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
