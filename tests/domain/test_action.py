"""Unit tests for :class:`sailguarding.domain.Action`.

An ``Action`` is the single self-similar unit of work: a goal is the root, a task is an
undecomposed node. We build a multi-level tree and assert the tree operations
(``is_root``/``is_leaf``, pre-order ``walk``, and ``find``).
"""

from __future__ import annotations

import pytest

from sailguarding.domain import Action


@pytest.fixture
def tree() -> Action:
    """A three-level tree.

    ship-update (root)
      ├─ write-tests
      │    ├─ context-tests (leaf)
      │    └─ event-tests (leaf)
      └─ update-docs (leaf)
    """
    context_tests = Action(id="context-tests", label="test context", parent_id="write-tests")
    event_tests = Action(id="event-tests", label="test events", parent_id="write-tests")
    write_tests = Action(
        id="write-tests",
        label="write the tests",
        parent_id="ship-update",
        children=(context_tests, event_tests),
    )
    update_docs = Action(id="update-docs", label="update the docs", parent_id="ship-update")
    return Action(
        id="ship-update",
        label="ship the update",
        children=(write_tests, update_docs),
    )


def test_root_defaults() -> None:
    root = Action(id="goal", label="a goal")

    assert root.parent_id is None
    assert root.children == ()
    assert root.is_root is True
    assert root.is_leaf is True


def test_root_of_tree_is_root_but_not_leaf(tree: Action) -> None:
    assert tree.is_root is True
    assert tree.is_leaf is False


@pytest.mark.parametrize(
    ("action_id", "expected_is_root", "expected_is_leaf"),
    [
        pytest.param("ship-update", True, False, id="root"),
        pytest.param("write-tests", False, False, id="intermediate"),
        pytest.param("context-tests", False, True, id="deep-leaf"),
        pytest.param("update-docs", False, True, id="shallow-leaf"),
    ],
)
def test_is_root_and_is_leaf(
    tree: Action,
    action_id: str,
    expected_is_root: bool,
    expected_is_leaf: bool,
) -> None:
    node = tree.find(action_id)
    assert node is not None
    assert node.is_root is expected_is_root
    assert node.is_leaf is expected_is_leaf


def test_walk_yields_depth_first_pre_order(tree: Action) -> None:
    assert [node.id for node in tree.walk()] == [
        "ship-update",
        "write-tests",
        "context-tests",
        "event-tests",
        "update-docs",
    ]


def test_walk_on_leaf_yields_only_itself() -> None:
    leaf = Action(id="solo", label="solo")

    assert list(leaf.walk()) == [leaf]


@pytest.mark.parametrize(
    "action_id",
    ["ship-update", "write-tests", "context-tests", "event-tests", "update-docs"],
)
def test_find_locates_every_node(tree: Action, action_id: str) -> None:
    found = tree.find(action_id)

    assert found is not None
    assert found.id == action_id


def test_find_locates_deep_node_identity(tree: Action) -> None:
    # The returned node is the very node in the tree, not a copy.
    write_tests = tree.find("write-tests")
    assert write_tests is not None
    assert tree.find("context-tests") is write_tests.children[0]


def test_find_returns_none_for_missing_id(tree: Action) -> None:
    assert tree.find("no-such-action") is None


def test_action_is_frozen(tree: Action) -> None:
    from dataclasses import FrozenInstanceError

    with pytest.raises(FrozenInstanceError):
        tree.label = "mutated"  # type: ignore[misc]
