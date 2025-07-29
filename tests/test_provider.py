import sys
from collections.abc import Iterable, Sequence
from random import Random
from typing import Optional

import pytest
from hypothesis import assume, given, settings, strategies as st
from hypothesis.control import BuildContext
from hypothesis.database import InMemoryExampleDatabase
from hypothesis.errors import FlakyBackendFailure
from hypothesis.internal.conjecture.choice import choice_equal, choice_permitted
from hypothesis.internal.conjecture.data import ConjectureData
from hypothesis.internal.reflection import function_digest
from strategies import choice_type_and_constraints, constraints_strategy, nodes

from hypofuzz import provider
from hypofuzz.coverage import CoverageCollector
from hypofuzz.database import (
    ChoicesT,
    FailureState,
    HypofuzzDatabase,
    Phase,
    test_keys_key,
)
from hypofuzz.hypofuzz import FuzzTarget
from hypofuzz.provider import HypofuzzProvider, QueuePriority


class EmptyCoverageCollector(CoverageCollector):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _assert_priority(target: FuzzTarget, priorities: Sequence[QueuePriority]) -> None:
    expected = [
        priority for (priority, _choices, _extra_data) in target.provider._choices_queue
    ]
    assert expected == priorities


@given(st.integers())
def _wrapped_test(n):
    pass


def _data(
    *,
    random: Optional[Random] = None,
    queue: Iterable[tuple[QueuePriority, ChoicesT]] = (),
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

    with BuildContext(ConjectureData.for_choices([]), wrapped_test=_wrapped_test):
        data.provider._startup()
    # remove the initial ChoiceTemplate(type="simplest") queue
    data.provider._choices_queue.clear()
    for priority, choices in queue:
        data.provider._enqueue(priority, choices)

    return data


@given(st.lists(nodes()))
@settings(deadline=None)
def test_drawing_prefix_exactly(nodes):
    # drawing exactly a prefix gives that prefix
    data = _data(queue=[(QueuePriority.COVERING, tuple(n.value for n in nodes))])
    with data.provider.per_test_case_context_manager():
        for node in nodes:
            choice = getattr(data, f"draw_{node.type}")(**node.constraints)
            assert choice_equal(node.value, choice)


@given(choice_type_and_constraints(), st.randoms())
@settings(deadline=None)
def test_draw_past_prefix(choice_type_and_constraints, random):
    # drawing past the prefix gives random (permitted) values
    choice_type, constraints = choice_type_and_constraints
    data = _data(random=random, queue=[(QueuePriority.COVERING, ())])

    with data.provider.per_test_case_context_manager():
        choice = getattr(data, f"draw_{choice_type}")(**constraints)

    assert choice_permitted(choice, constraints)


@given(nodes(), choice_type_and_constraints(), st.randoms())
@settings(deadline=None)
def test_misaligned_type(node, choice_type_constraints, random):
    # misaligning in type gives us random values
    choice_type, constraints = choice_type_constraints
    assume(choice_type != node.type)
    data = _data(random=random, queue=[(QueuePriority.COVERING, (node.value,))])

    with data.provider.per_test_case_context_manager():
        choice = getattr(data, f"draw_{choice_type}")(**constraints)

    assert choice_permitted(choice, constraints)


@given(st.data(), nodes(), st.randoms())
@settings(deadline=None)
def test_misaligned_constraints(data, node, random):
    # misaligning in constraints gives us random values
    constraints = data.draw(constraints_strategy(node.type))
    assume(not choice_permitted(node.value, constraints))

    data = _data(random=random, queue=[(QueuePriority.COVERING, (node.value,))])
    with data.provider.per_test_case_context_manager():
        choice = getattr(data, f"draw_{node.type}")(**constraints)

    assert choice_permitted(choice, constraints)


@given(st.data(), nodes(), st.randoms())
@settings(deadline=None)
def test_changed_constraints_pops_if_still_permitted(data, node, random):
    # changing constraints to something that still permits the value still pops the value
    constraints = data.draw(constraints_strategy(node.type))
    assume(choice_permitted(node.value, constraints))

    data = _data(random=random, queue=[(QueuePriority.COVERING, (node.value,))])
    with data.provider.per_test_case_context_manager():
        choice = getattr(data, f"draw_{node.type}")(**constraints)

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
    @settings(backend="hypofuzz", database=db)
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
        # non-timed reports might be saved either because they found a new behavior
        # or a new fingerprint
        assert (
            report1.behaviors < report2.behaviors
            or report1.fingerprints < report2.fingerprints
        )


def test_provider_multiple_executions():
    data = _data(
        queue=[(QueuePriority.COVERING, (1,)), (QueuePriority.COVERING, (2,))],
    )

    with data.provider.per_test_case_context_manager():
        assert data.draw_integer() == 1

    with data.provider.per_test_case_context_manager():
        assert data.draw_integer() == 2


def test_stability_replays_exact_choices():
    calls = []

    @given(st.integers())
    def test_a(n):
        if n == 10:
            pass
        calls.append(n)

    target = FuzzTarget.from_hypothesis_test(
        test_a, database=HypofuzzDatabase(InMemoryExampleDatabase())
    )
    target._enter_fixtures()
    target._execute_once(target.new_conjecture_data(choices=[10]))
    # executing again should execute the stability queue
    target._execute_once(target.new_conjecture_data())

    assert calls == [10, 10]


@pytest.mark.skipif(
    sys.version_info < (3, 12), reason="different branches without sys.monitoring"
)
def test_stability_only_adds_behaviors_on_replay():
    @given(st.integers())
    def test_a(n):
        if n == 10:
            pass

    target = FuzzTarget.from_hypothesis_test(
        test_a, database=HypofuzzDatabase(InMemoryExampleDatabase())
    )
    target._enter_fixtures()

    target._execute_once(target.new_conjecture_data(choices=[10]))
    # added to queue with QueuePriority.COVERING_REPLAY
    assert list(target.provider.corpus.behavior_counts.values()) == []

    target._execute_once(target.new_conjecture_data())
    # replaying choices=[10] from the queue for stability
    assert list(target.provider.corpus.behavior_counts.values()) == [1]

    target._execute_once(target.new_conjecture_data(choices=[10]))
    # no new behavior, so it increments behavior_counts
    assert list(target.provider.corpus.behavior_counts.values()) == [2]


def test_invalid_data_does_not_add_coverage():
    @given(st.integers())
    def test_a(x):
        if x > 0:
            pass
        else:
            pass
        assume(False)

    target = FuzzTarget.from_hypothesis_test(
        test_a, database=HypofuzzDatabase(InMemoryExampleDatabase())
    )
    target._enter_fixtures()

    for choices in [[1], [-1], *([None] * 5)]:
        target._execute_once(target.new_conjecture_data(choices=choices))
        assert not target.provider.corpus.behavior_counts
        assert not target.provider.corpus.fingerprints


def test_backend_setting_can_fail():
    db = InMemoryExampleDatabase()

    @given(st.integers())
    @settings(backend="hypofuzz", database=db)
    def f(n):
        assert n < 100, "unique identifier"

    with pytest.raises(AssertionError, match="unique identifier"):
        f()

    key = list(db.data[test_keys_key])[0]
    hypofuzz_db = HypofuzzDatabase(db)
    failures = list(
        hypofuzz_db.fetch_failures(key, state=FailureState.UNSHRUNK)
    ) + list(hypofuzz_db.fetch_failures(key, state=FailureState.SHRUNK))
    assert failures


def test_explicit_backend_errors_without_db():
    @given(st.integers())
    @settings(database=None, backend="hypofuzz")
    def f(n):
        pass

    # validation errors raised by backends are treated as failures and replayed
    # by hypothesis. Maybe we need a BackendValidationError which is not replayed,
    # or a separate PrimitiveProvider.validate method? (careful about where in
    # the lifecycle the latter fits; needs access to the test function and settings).
    with pytest.raises(FlakyBackendFailure):
        f()


@pytest.mark.skipif(sys.version_info < (3, 10), reason="different branches on 3.9?")
def test_does_not_switch_to_generate_when_replaying():
    @given(st.integers())
    def test_a(n):
        if n == 10:
            pass

    db = HypofuzzDatabase(InMemoryExampleDatabase())
    target = FuzzTarget.from_hypothesis_test(test_a, database=db)

    db.save_corpus(target.database_key, [2])
    db.save_corpus(target.database_key, [10])
    target._enter_fixtures()

    # we start in this state conceptually, except the provider hasn't loaded from
    # the db yet, so we can't assert it.
    # _assert_priority([QueuePriority.COVERING_REPLAY, QueuePriority.COVERING_REPLAY])

    # we pop the first COVERING_REPLAY element [2]. It discovers new coverage, so gets
    # re-queued as STABILITY.
    target.run_one()
    _assert_priority(target, [QueuePriority.STABILITY, QueuePriority.COVERING_REPLAY])
    assert target.provider.phase is Phase.REPLAY

    # we pop the STABILITY element [2], adding it to the corpus.
    target.run_one()
    _assert_priority(target, [QueuePriority.COVERING_REPLAY])
    assert target.provider.phase is Phase.REPLAY

    # we pop the COVERING_REPLAY element [10]. It also discovers new coverage, and
    # gets re-queued as STABILITY.
    target.run_one()
    _assert_priority(target, [QueuePriority.STABILITY])
    assert target.provider.phase is Phase.REPLAY

    # we pop the STABILITY element [10], adding it to the corpus. This completes
    # our queue.
    target.run_one()
    _assert_priority(target, [])
    assert target.provider.phase is Phase.REPLAY

    # we have no more queue elements left, so we transition into Phase.GENERATE.
    target.run_one()
    _assert_priority(target, [])
    assert target.provider.phase is Phase.GENERATE
