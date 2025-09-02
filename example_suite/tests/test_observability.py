from hypothesis import assume, event, given, strategies as st, target


@given(st.lists(st.integers()), st.integers(), st.integers(), st.data())
def test_many_observability_features(l, a, x, data):
    event(f"{x%2=}")
    target(x % 5, label="x%5")
    assume(a % 9)
    assume(len(l) > 0)
    data.draw(st.text("abcdef", min_size=a % 3), label="interactive")
