from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, rule


class SimpleStateMachine(RuleBasedStateMachine):
    @rule(n=st.integers())
    def step(self, n):
        assert isinstance(n, int)


TestStatefulSimple = SimpleStateMachine.TestCase
