"""The recursive unit of work.

There is exactly one self-similar type. A **goal** is just the root action; a **task** is
just a node we have not decomposed further. Root or leaf, every node is an ``Action`` with
children. We do not model "goal" and "task" as separate concepts.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Action:
    """A node in the action tree.

    :param id: Stable identifier, unique within a tree.
    :param label: Human-readable description ("write the tests", "ship the update").
    :param parent_id: ``None`` at the root; the parent's ``id`` otherwise.
    :param children: Sub-actions this decomposes into; empty for a leaf.
    """

    id: str
    label: str
    parent_id: str | None = None
    children: tuple[Action, ...] = field(default_factory=tuple)

    @property
    def is_root(self) -> bool:
        return self.parent_id is None

    @property
    def is_leaf(self) -> bool:
        return not self.children

    def walk(self) -> Iterator[Action]:
        """Yield this action, then every descendant, depth-first (pre-order)."""
        yield self
        for child in self.children:
            yield from child.walk()

    def find(self, action_id: str) -> Action | None:
        """Return the action with ``action_id`` in this subtree, or ``None``."""
        for node in self.walk():
            if node.id == action_id:
                return node
        return None
