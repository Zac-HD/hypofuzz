from hypothesis import assume, given, strategies as st
from hypothesis.internal.conjecture.choice import choice_equal, choice_permitted
from hypothesis.internal.conjecture.data import ConjectureData
from strategies import ir_types_and_kwargs, kwargs_strategy, nodes

from hypofuzz.provider import HypofuzzProvider


@given(st.lists(nodes()))
def test_drawing_prefix_exactly(nodes):
    # drawing exactly a prefix gives that prefix
    cd = ConjectureData(
        random=None,
        provider=HypofuzzProvider,
        provider_kw={"choices": tuple(n.value for n in nodes)},
    )
    for node in nodes:
        choice = getattr(cd, f"draw_{node.ir_type}")(**node.kwargs)
        assert choice_equal(node.value, choice)


@given(ir_types_and_kwargs(), st.randoms())
def test_draw_past_prefix(ir_type_and_kwargs, random):
    # drawing past the prefix gives random (permitted) values
    ir_type, kwargs = ir_type_and_kwargs
    cd = ConjectureData(
        random=random, provider=HypofuzzProvider, provider_kw={"choices": ()}
    )
    choice = getattr(cd, f"draw_{ir_type}")(**kwargs)
    assert choice_permitted(choice, kwargs)


@given(nodes(), ir_types_and_kwargs(), st.randoms())
def test_misaligned_type(node, ir_type_kwargs, random):
    # misaligning in type gives us random values
    ir_type, kwargs = ir_type_kwargs
    assume(ir_type != node.ir_type)
    cd = ConjectureData(
        random=random, provider=HypofuzzProvider, provider_kw={"choices": (node.value,)}
    )
    choice = getattr(cd, f"draw_{ir_type}")(**kwargs)
    assert choice_permitted(choice, kwargs)


@given(st.data())
def test_misaligned_kwargs(data):
    # misaligning in permitted kwargs gives us random values
    node = data.draw(nodes())
    kwargs = data.draw(kwargs_strategy(node.ir_type))
    assume(not choice_permitted(node.value, kwargs))
    cd = ConjectureData(
        random=data.draw(st.randoms()),
        provider=HypofuzzProvider,
        provider_kw={"choices": (node.value,)},
    )
    choice = getattr(cd, f"draw_{node.ir_type}")(**kwargs)
    assert choice_permitted(choice, kwargs)


@given(st.data())
def test_changed_kwargs_pops_if_still_permitted(data):
    # changing kwargs to something that still permits the value still pops the value
    node = data.draw(nodes())
    kwargs = data.draw(kwargs_strategy(node.ir_type))
    assume(choice_permitted(node.value, kwargs))
    cd = ConjectureData(
        random=data.draw(st.randoms()),
        provider=HypofuzzProvider,
        provider_kw={"choices": (node.value,)},
    )
    choice = getattr(cd, f"draw_{node.ir_type}")(**kwargs)
    assert choice_equal(choice, node.value)
