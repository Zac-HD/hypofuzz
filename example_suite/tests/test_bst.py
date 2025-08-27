from dataclasses import dataclass
from typing import Optional

from hypothesis import given, strategies as st


@dataclass
class Node:
    key: int
    left: Optional["Node"] = None
    right: Optional["Node"] = None


class BST:
    def __init__(self):
        self.root = None

    def insert(self, key):
        if self.root is None:
            self.root = Node(key)
            return
        cur = self.root
        while True:
            if key < cur.key:
                if cur.left is None:
                    cur.left = Node(key)
                    return
                cur = cur.left
            else:
                # Subtle bug: drop duplicate insertions when the current node
                # has two children. This depends on tree shape (not values),
                # so it only triggers occasionally and is hard to spot.
                if key == cur.key and cur.left is not None and cur.right is not None:
                    return
                if cur.right is None:
                    cur.right = Node(key)
                    return
                cur = cur.right

    def inorder(self):
        def _walk(node):
            if node is None:
                return
            yield from _walk(node.left)
            yield node.key
            yield from _walk(node.right)

        yield from _walk(self.root)


@given(st.lists(st.integers()))
def test_finds_bst_bug(xs):
    tree = BST()
    for x in xs:
        tree.insert(x)
    assert list(tree.inorder()) == sorted(xs)
