"""The activity tree — a persistable, navigable wrapper around a root :class:`Activity`.

Task 01 gave us the recursive :class:`Activity` node; nothing yet *built* a tree, persisted one, or
walked *up* it. This module does all three:

- **Navigation up the tree.** Budget inheritance (:mod:`.budget`) needs a node's ancestors, but an
  :class:`Activity` only knows its ``parent_id``, not the parent object.
  :meth:`ActivityTree.path_to_root` resolves the chain from a node to the root, which is what
  inheritance walks.
- **Persistence.** :class:`ActivityTree` is versioned, serialisable, and round-trip stable
  (``ActivityTree.from_dict(t.to_dict()) == t``), so a tree can be stored and reloaded. The nested
  :class:`Activity` nodes serialise recursively here rather than on the domain type, keeping
  :class:`Activity` a pure in-memory unit.
- **Growth.** :meth:`ActivityTree.graft` returns a new tree with a child added under a parent, the
  operation the bottom-up seeding path (:mod:`.seed`) uses to turn a triaged event into a named node
  in the tree.

The tree is domain-agnostic on purpose: "ship a regulation-compliant update" decomposes into
"write the tests" exactly as "buy a sofa" decomposes into "pick the fabric".
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from sailguarding.domain import Activity

# Bumped whenever the serialised shape of an ActivityTree changes, so a reader can tell which schema
# produced a stored tree.
ACTIVITY_TREE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ActivityTree:
    """A whole activity tree: one root :class:`Activity` plus navigation and persistence.

    :param root: The root activity; its ``children`` carry the rest of the tree.
    :param schema_version: The record schema version; defaults to the current one.
    """

    root: Activity
    schema_version: int = field(default=ACTIVITY_TREE_SCHEMA_VERSION)

    def walk(self) -> Iterator[Activity]:
        """Every node, depth-first pre-order (delegates to :meth:`Activity.walk`)."""
        return self.root.walk()

    def find(self, activity_id: str) -> Activity | None:
        """The node with ``activity_id``, or ``None`` if it is not in the tree."""
        return self.root.find(activity_id)

    def parent_of(self, activity_id: str) -> Activity | None:
        """The parent of ``activity_id``, or ``None`` at the root / for a missing node."""
        node = self.find(activity_id)
        if node is None or node.parent_id is None:
            return None
        return self.find(node.parent_id)

    def path_to_root(self, activity_id: str) -> list[Activity]:
        """The chain from ``activity_id`` up to the root: ``[node, parent, …, root]``.

        Empty if the node is not in the tree. This is the order budget inheritance walks — the node
        first, so its own declaration overrides what it would inherit.
        """
        node = self.find(activity_id)
        if node is None:
            return []
        chain = [node]
        while chain[-1].parent_id is not None:
            parent = self.find(chain[-1].parent_id)
            if parent is None:  # dangling parent_id; stop rather than loop
                break
            chain.append(parent)
        return chain

    def graft(self, parent_id: str, child: Activity) -> ActivityTree:
        """A new tree with ``child`` added under ``parent_id`` (this tree is left unchanged).

        The nodes on the path from the root to the parent are rebuilt (they are frozen), so grafting
        is a pure, value-returning operation. ``child.parent_id`` is set to ``parent_id`` so the new
        node is consistent regardless of what the caller passed. Raises :class:`KeyError` if
        ``parent_id`` is not in the tree.
        """
        if self.find(parent_id) is None:
            raise KeyError(f"no activity {parent_id!r} in tree to graft under")
        seated = _reparent(child, parent_id)
        return ActivityTree(
            root=_add_child(self.root, parent_id, seated),
            schema_version=self.schema_version,
        )

    def to_dict(self) -> dict[str, Any]:
        """A JSON-compatible dict; the root serialises recursively."""
        return {
            "schema_version": self.schema_version,
            "root": _action_to_dict(self.root),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ActivityTree:
        """Rebuild a tree from :meth:`to_dict` output, rejecting an unknown schema version."""
        version = data.get("schema_version", ACTIVITY_TREE_SCHEMA_VERSION)
        if version != ACTIVITY_TREE_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported ActivityTree schema_version {version!r}; "
                f"this build reads version {ACTIVITY_TREE_SCHEMA_VERSION}"
            )
        return cls(root=_action_from_dict(data["root"]), schema_version=version)

    def to_json(self) -> str:
        """Serialise to a canonical, single-line JSON string (sorted keys, tight separators)."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> ActivityTree:
        """Parse a tree from a JSON string produced by :meth:`to_json`."""
        return cls.from_dict(json.loads(text))


@runtime_checkable
class ActivityTreeStore(Protocol):
    """Persist and reload a single :class:`ActivityTree`.

    The minimal contract — save one, load it back — so a durable store (a git branch, a file) can
    implement the same shape later without the engine caring which backs it.
    """

    def save(self, tree: ActivityTree) -> None:
        """Persist ``tree``, replacing any previously saved one."""
        ...

    def load(self) -> ActivityTree | None:
        """The saved tree, or ``None`` if nothing has been saved yet."""
        ...


class InMemoryActivityTreeStore:
    """An :class:`ActivityTreeStore` holding the tree in memory.

    The injectable default: nothing shared between instances, and the tree is round-tripped through
    its serialised form on save so a test exercises the real encode/decode path with no I/O.
    """

    def __init__(self) -> None:
        self._payload: str | None = None

    def save(self, tree: ActivityTree) -> None:
        self._payload = tree.to_json()

    def load(self) -> ActivityTree | None:
        if self._payload is None:
            return None
        return ActivityTree.from_json(self._payload)


def _action_to_dict(activity: Activity) -> dict[str, Any]:
    """Serialise an :class:`Activity` and its subtree recursively."""
    data: dict[str, Any] = {"id": activity.id, "label": activity.label}
    if activity.parent_id is not None:
        data["parent_id"] = activity.parent_id
    if activity.children:
        data["children"] = [_action_to_dict(child) for child in activity.children]
    return data


def _action_from_dict(data: Mapping[str, Any]) -> Activity:
    """Rebuild an :class:`Activity` and its subtree from :func:`_action_to_dict` output."""
    return Activity(
        id=data["id"],
        label=data["label"],
        parent_id=data.get("parent_id"),
        children=tuple(_action_from_dict(child) for child in data.get("children", ())),
    )


def _reparent(activity: Activity, parent_id: str) -> Activity:
    """A copy of ``activity`` whose ``parent_id`` is ``parent_id`` (subtree untouched)."""
    return Activity(
        id=activity.id,
        label=activity.label,
        parent_id=parent_id,
        children=activity.children,
    )


def _add_child(node: Activity, parent_id: str, child: Activity) -> Activity:
    """Rebuild ``node``'s subtree, appending ``child`` to the node whose id is ``parent_id``."""
    if node.id == parent_id:
        return Activity(
            id=node.id,
            label=node.label,
            parent_id=node.parent_id,
            children=(*node.children, child),
        )
    return Activity(
        id=node.id,
        label=node.label,
        parent_id=node.parent_id,
        children=tuple(_add_child(c, parent_id, child) for c in node.children),
    )
