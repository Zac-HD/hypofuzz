from hypothesis import given, strategies as st

from example_suite.src.example_suite import pyyaml as yaml


@given(st.text())
def test_yaml_roundtrip(s):
    assert yaml.safe_load(yaml.dump(s)) == s
