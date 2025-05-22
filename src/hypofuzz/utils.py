import math
from typing import Any

FUZZJSON_INF = "hypofuzz-inf-a928fa52b3ea4a9a9af36ccef7c6cf93"
FUZZJSON_NINF = "hypofuzz-ninf-a928fa52b3ea4a9a9af36ccef7c6cf93"
FUZZJSON_NAN = "hypofuzz-nan-a928fa52b3ea4a9a9af36ccef7c6cf93"


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
