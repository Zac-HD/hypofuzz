from hypothesis import given, strategies as st

from example_suite.src.example_suite import json

json_strategy = st.deferred(
    lambda: st.none() | st.floats(allow_nan=False) | st.text() | lists | objects
)
lists = st.lists(json_strategy)
objects = st.dictionaries(st.text(), json_strategy)


@given(json_strategy)
def test_json_roundtrip_fails_on_inf(json_value):
    assert json.loads(json.dumps(json_value)) == json_value
