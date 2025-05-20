from hypothesis import (
    HealthCheck,
    assume,
    event,
    given,
    settings,
    strategies as st,
    target,
)


@given(st.lists(st.integers()), st.integers(), st.integers(), st.data())
def test_visual_tyche_grab_bag(l, a, x, data):
    event(f"{x%2=}")
    target(x % 5, label="x%5")
    assume(a % 9)
    assume(len(l) > 0)
    data.draw(st.text("abcdef", min_size=a % 3), label="interactive")


@settings(suppress_health_check=[HealthCheck.filter_too_much])
@given(st.integers())
def test_visual_tyche_almost_always_invalid(n):
    # we can't actually do assume(False), or hypothesis would error.
    # (and we can't xfail that because then hypofuzz won't collect it).
    assume(n == 0)
