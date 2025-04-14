from hypofuzz.coverage import CoverageCollectionContext

# ruff: noqa: PLW0120, E701

# The way to read the branch format for these tests is:
#  ((source_line, source_column), (destination_line, destination_column))


class Collector:
    def __init__(self, f):
        self.offset = f.__code__.co_firstlineno
        self.context = CoverageCollectionContext()

    @property
    def branches(self) -> set[tuple[tuple[int, int], tuple[int, int]]]:
        files = set()
        branches = set()
        for start, end in self.context.branches:
            files.add(start[0])
            files.add(end[0])
            branches.add(
                ((start[1] - self.offset, start[2]), (end[1] - self.offset, end[2]))
            )
        # all branches are in the same file
        assert len(files) <= 1
        return branches

    def __enter__(self) -> "Collector":
        self.context.__enter__()
        return self

    def __exit__(self, *args, **kwargs):
        return self.context.__exit__(*args, **kwargs)


def test_branchless():
    def f():
        pass
        pass
        pass

    with Collector(f) as collector:
        f()
    assert collector.branches == set()


def test_branchless_nested_function():
    def f():
        pass

        def g():
            return 1

        g()
        pass

    with Collector(f) as collector:
        f()
    assert collector.branches == set()


def test_branchless_unconditional_true():
    # I think the interpreter optimizes this branch out.
    def f():
        if True:
            pass

    with Collector(f) as collector:
        f()
    assert collector.branches == set()


def test_branchless_unconditional_false():
    def f():
        if False:
            pass

    with Collector(f) as collector:
        f()
    assert collector.branches == set()


def test_if():
    def f(x):
        if x == 1:
            pass
        pass

    # false
    with Collector(f) as collector:
        f(0)
    assert collector.branches == {((1, 11), (3, 8))}

    # true
    with Collector(f) as collector:
        f(1)
    assert collector.branches == {((1, 11), (2, 12))}


def test_if_oneline():
    # fmt: off
    def f(x):
        if x == 1: pass
        pass
    # fmt: on

    # false
    with Collector(f) as collector:
        f(0)
    assert collector.branches == {((1, 11), (2, 8))}

    # true
    with Collector(f) as collector:
        f(1)
    assert collector.branches == {((1, 11), (1, 19))}


def test_if_ternary():
    def f(x):
        return 1 if x == 1 else 0

    # false
    with Collector(f) as collector:
        f(0)
    assert collector.branches == {((1, 20), (1, 32))}

    # true
    with Collector(f) as collector:
        f(1)
    assert collector.branches == {((1, 20), (1, 15))}


def test_if_with_else():
    def f(x):
        if x == 1:  # L1
            pass  # L2
        else:
            pass  # L4

    # false
    with Collector(f) as collector:
        f(0)
    assert collector.branches == {((1, 11), (4, 12))}

    # true
    with Collector(f) as collector:
        f(1)
    assert len(collector.branches) == 1
    assert collector.branches == {((1, 11), (2, 12))}


def test_if_nested():
    def f(x):
        if x == 1:
            if x == 1:
                pass  # L3
            else:
                pass  # L5
        else:
            pass  # L7
        pass

    # false
    collector = Collector(f)
    with collector:
        f(0)
    assert collector.branches == {((1, 11), (7, 12))}

    # true
    collector = Collector(f)
    with collector:
        f(1)
    assert collector.branches == {((1, 11), (2, 15)), ((2, 15), (3, 16))}


def test_while():
    def f():
        n = 0
        while n < 5:
            n += 1
        pass

    collector = Collector(f)
    with collector:
        f()
    assert collector.branches == {
        # I'm not sure what this (2, 14) self-reference branch is for. TODO look
        # at the bytecode here
        ((2, 14), (2, 14)),
        ((2, 14), (3, 12)),
        ((2, 14), (4, 8)),
    }


def test_while_initial_false():
    def f(x):
        while x == 1:
            pass
        pass

    collector = Collector(f)
    with collector:
        f(0)
    assert collector.branches == {((1, 14), (3, 8))}


def test_for_no_else_no_break():
    # `for` branches from the `for` statement itself to:
    # * the definition of the loop variable `_`, during a loop iteration
    # * the `pass` statement after the loop, when the loop ends
    def f():
        for _ in range(10):
            pass
        pass

    with Collector(f) as collector:
        f()
    assert collector.branches == {((1, 8), (3, 8)), ((1, 8), (1, 12))}


def test_for_no_else_break():
    # Ideally the break statement would generate a branch ((2, 12), (3, 8)) here,
    # but it doesn't. See test_for_loop_break_does_not_branch.
    def f():
        for _ in range(10):
            break
        pass

    with Collector(f) as collector:
        f()
    assert collector.branches == {((1, 8), (1, 12))}


def test_for_else_no_break():
    def f():
        for _ in range(10):  # L1
            pass  # L2
        else:
            pass  # L4
        pass

    with Collector(f) as collector:
        f()
    assert collector.branches == {((1, 8), (1, 12)), ((1, 8), (4, 12))}


def test_for_else_break():
    def f():
        for _ in range(10):
            break
        else:
            pass
        pass

    with Collector(f) as collector:
        f()
    assert collector.branches == {((1, 8), (1, 12))}


def test_for_loop_break_does_not_branch():
    # `break` inside of a for loop does not generate a branch event. This is
    # unfortunate for us, because we can't distinguish a for loop which completes
    # normally from a for loop which breaks early.
    def f(*, should_break):
        for i in range(10):
            if i == 5 and should_break:
                break
        pass

    with Collector(f) as collector:
        f(should_break=False)
    branches = collector.branches

    with Collector(f) as collector:
        f(should_break=False)
    # this assertion is descriptive, not perscriptive. We wish there was a new
    # branch here.
    assert collector.branches == branches


def test_or():
    def f(x):
        a = x or 42
        return a

    with Collector(f) as collector:
        f(False)
    # A false value does not short circuit, so we go on to evaluate...`x` again?
    # Maybe a STORE? TODO check the bytecode here to ensure I understand correctly
    assert collector.branches == {((1, 12), (1, 12))}

    # A true value short circuits and goes back to `a`
    with Collector(f) as collector:
        f(True)
    assert collector.branches == {((1, 12), (1, 8))}


def test_and():
    def f(x):
        a = x and 42
        return a

    with Collector(f) as collector:
        f(False)
    assert collector.branches == {((1, 12), (1, 8))}

    with Collector(f) as collector:
        f(True)
    assert collector.branches == {((1, 12), (1, 12))}
