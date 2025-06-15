from collections.abc import Iterable
from random import Random

from hypothesis import assume, given, settings, strategies as st
from hypothesis.database import InMemoryExampleDatabase
from hypothesis.internal.conjecture.choice import choice_equal, choice_permitted
from hypothesis.internal.conjecture.data import ConjectureData
from hypothesis.internal.reflection import function_digest
from strategies import choice_type_and_constraints, constraints_strategy, nodes

from hypofuzz import provider
from hypofuzz.coverage import CoverageCollector
from hypofuzz.database import HypofuzzDatabase
from hypofuzz.provider import HypofuzzProvider, ReplayPriority, ReplayQueueElement


class EmptyCoverageCollector(CoverageCollector):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def hypofuzz_data(
    random: Random, *, queue: Iterable[ReplayQueueElement] = ()
) -> ConjectureData:
    data = ConjectureData(
        random=random,
        provider=HypofuzzProvider,
        # We're calling provider.per_test_case_manager
        # in test cases, which works fine when running normally through pytest,
        # but not when running through hypofuzz, since there is a sys.monitoring
        # tool collision in our coverage collection.
        #
        # We don't rely on coverage collection in these tests, so disable it to
        # support both modes of running the tests.
        provider_kw={"collector": EmptyCoverageCollector()},
    )
    assert isinstance(data.provider, HypofuzzProvider)
    # force HypofuzzProvider to load from the db now, so we can control the
    # queue for tests
    data.provider._startup()
    # remove the initial ChoiceTemplate(type="simplest") queue
    data.provider._replay_queue.clear()
    for priority, choices in queue:
        data.provider._enqueue(priority, choices)

    return data


@given(st.lists(nodes()))
@settings(deadline=None)
def test_drawing_prefix_exactly(nodes):
    # drawing exactly a prefix gives that prefix
    data = hypofuzz_data(
        random=None, queue=[(ReplayPriority.COVERING, tuple(n.value for n in nodes))]
    )

    with data.provider.per_test_case_context_manager():
        for node in nodes:
            choice = getattr(data, f"draw_{node.type}")(**node.constraints)
            assert choice_equal(node.value, choice)


@given(choice_type_and_constraints(), st.randoms())
@settings(deadline=None)
def test_draw_past_prefix(choice_type_and_constraints, random):
    # drawing past the prefix gives random (permitted) values
    choice_type, constraints = choice_type_and_constraints
    data = hypofuzz_data(random=random, queue=[(ReplayPriority.COVERING, ())])

    with data.provider.per_test_case_context_manager():
        choice = getattr(data, f"draw_{choice_type}")(**constraints)

    assert choice_permitted(choice, constraints)


@given(nodes(), choice_type_and_constraints(), st.randoms())
@settings(deadline=None)
def test_misaligned_type(node, ir_type_kwargs, random):
    # misaligning in type gives us random values
    ir_type, kwargs = ir_type_kwargs
    assume(ir_type != node.type)
    cdata = hypofuzz_data(
        random=random, queue=[(ReplayPriority.COVERING, (node.value,))]
    )

    with cdata.provider.per_test_case_context_manager():
        choice = getattr(cdata, f"draw_{ir_type}")(**kwargs)

    assert choice_permitted(choice, kwargs)


@given(st.data())
@settings(deadline=None)
def test_misaligned_kwargs(data):
    # misaligning in permitted kwargs gives us random values
    node = data.draw(nodes())
    kwargs = data.draw(constraints_strategy(node.type))
    assume(not choice_permitted(node.value, kwargs))
    data = hypofuzz_data(
        random=data.draw(st.randoms()), queue=[(ReplayPriority.COVERING, (node.value,))]
    )

    with data.provider.per_test_case_context_manager():
        choice = getattr(data, f"draw_{node.type}")(**kwargs)

    assert choice_permitted(choice, kwargs)


@given(st.data())
@settings(deadline=None)
def test_changed_kwargs_pops_if_still_permitted(data):
    # changing kwargs to something that still permits the value still pops the value
    node = data.draw(nodes())
    kwargs = data.draw(constraints_strategy(node.type))
    assume(choice_permitted(node.value, kwargs))
    data = hypofuzz_data(
        random=data.draw(st.randoms()), queue=[(ReplayPriority.COVERING, (node.value,))]
    )

    with data.provider.per_test_case_context_manager():
        choice = getattr(data, f"draw_{node.type}")(**kwargs)

    assert choice_equal(choice, node.value)


def test_provider_loads_from_database():
    n = 123456789
    db = InMemoryExampleDatabase()
    hypofuzz_db = HypofuzzDatabase(db)
    values = set()

    @given(st.integers())
    @settings(backend="hypofuzz", database=db, max_examples=10)
    def f(n):
        values.add(n)

    hypofuzz_db.save_corpus(function_digest(f.hypothesis.inner_test), (n,))
    f()
    assert n in values


def test_provider_deletes_old_timed_reports(monkeypatch):
    db = InMemoryExampleDatabase()
    hypofuzz_db = HypofuzzDatabase(db)
    monkeypatch.setattr(
        provider, "_should_save_timed_report", lambda elapsed_time, last_saved_at: True
    )

    @given(st.integers())
    @settings(backend="hypofuzz", database=db, max_examples=100)
    def f(n):
        if n == 0:
            pass
        elif 0 < n <= 10:
            pass
        elif 10 < n <= 50:
            pass
        elif 50 < n <= 100:
            pass

    f()
    reports = hypofuzz_db.fetch_reports(function_digest(f.hypothesis.inner_test))
    reports = sorted(reports, key=lambda r: r.elapsed_time)

    # explicitly use `- 2` instead of `- 1` here. We do not want to compare
    # the second to last report to the last report, because the last report is
    # likely to be a timed report, in which case it is valid for it to have the
    # same behaviors and fingerprints as its predecessor.
    for i in range(len(reports) - 2):
        report1 = reports[i]
        report2 = reports[i + 1]
        assert report1.elapsed_time < report2.elapsed_time
        assert report1.behaviors < report2.behaviors
        assert report1.fingerprints < report2.fingerprints
