import math

from hypothesis import event, given
from hypothesis.strategies import floats


# json.parse can't accept math.nan or math.inf, so we transform those into
# unique identifiers. This visual test checks that we correctly transform on both
# ends, so the user never sees the unique identifier.
@given(floats())
def test_floats(v):
    if math.isnan(v):
        event("math.nan", v)
    elif math.isinf(v) and v > 0:
        event("+math.inf", v)
    elif math.isinf(v) and v < 0:
        event("-math.inf", v)
