import pytest
from hypothesis import given, note, strategies as st

from hypofuzz.bayes import softmax


@given(st.lists(st.floats(min_value=0, allow_nan=False, allow_infinity=False)))
def test_softmax(values):
    softmaxed = softmax(values)
    note(f"{softmaxed=}")
    assert all(0 <= v <= 1 for v in softmaxed)

    # check that softmax preserves ordering
    for i in range(len(values) - 1):
        if values[i] == values[i + 1]:
            assert softmaxed[i] == softmaxed[i + 1]
        if values[i] < values[i + 1]:
            # note <= and not < here, since softmax may round down small
            # differences in values to 0
            assert softmaxed[i] <= softmaxed[i + 1]
        if values[i] > values[i + 1]:
            assert softmaxed[i] >= softmaxed[i + 1]

    if values:
        assert sum(softmaxed) == pytest.approx(1)
