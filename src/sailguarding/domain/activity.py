"""The recursive unit of work.

There is exactly one self-similar type. A **goal** is just the root activity; a **task** is
just a node we have not decomposed further. Root or leaf, every node is an ``Activity`` with
children. We do not model "goal" and "task" as separate concepts.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Activity:
    """A node in the activity tree.

    :param id: Stable identifier, unique within a tree.
    :param label: Human-readable description ("write the tests", "ship the update").
    :param parent_id: ``None`` at the root; the parent's ``id`` otherwise.
    :param children: Sub-activities this decomposes into; empty for a leaf.
    """

    id: str
    label: str
    parent_id: str | None = None
    children: tuple[Activity, ...] = field(default_factory=tuple)

    @property
    def is_root(self) -> bool:
        return self.parent_id is None

    @property
    def is_leaf(self) -> bool:
        return not self.children

    def walk(self) -> Iterator[Activity]:
        """Yield this activity, then every descendant, depth-first (pre-order)."""
        yield self
        for child in self.children:
            yield from child.walk()

    def find(self, activity_id: str) -> Activity | None:
        """Return the activity with ``activity_id`` in this subtree, or ``None``."""
        for node in self.walk():
            if node.id == activity_id:
                return node
        return None
