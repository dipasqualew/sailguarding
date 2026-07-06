"""Unit tests for :class:`ActionTree`: navigation, growth, and round-trip serialisation."""

from __future__ import annotations

import pytest

from sailguarding.domain import Action
from sailguarding.tree import (
    ACTION_TREE_SCHEMA_VERSION,
    ActionTree,
    ActionTreeStore,
    InMemoryActionTreeStore,
)


@pytest.fixture
def tree() -> ActionTree:
    """The SPEC worked example as a tree.

    ship-update (root)
      ├─ write-tests
      │    └─ context-tests (leaf)
      └─ update-docs (leaf)
    """
    context_tests = Action(id="context-tests", label="test context", parent_id="write-tests")
    write_tests = Action(
        id="write-tests",
        label="write the tests",
        parent_id="ship-update",
        children=(context_tests,),
    )
    update_docs = Action(id="update-docs", label="update the docs", parent_id="ship-update")
    root = Action(id="ship-update", label="ship the update", children=(write_tests, update_docs))
    return ActionTree(root)


def test_find_and_walk_delegate_to_the_root(tree: ActionTree) -> None:
    assert [n.id for n in tree.walk()] == [
        "ship-update",
        "write-tests",
        "context-tests",
        "update-docs",
    ]
    assert tree.find("context-tests") is not None
    assert tree.find("nope") is None


def test_parent_of(tree: ActionTree) -> None:
    assert tree.parent_of("context-tests").id == "write-tests"  # type: ignore[union-attr]
    assert tree.parent_of("write-tests").id == "ship-update"  # type: ignore[union-attr]
    assert tree.parent_of("ship-update") is None  # root has no parent
    assert tree.parent_of("missing") is None


def test_path_to_root_is_node_first_then_ancestors(tree: ActionTree) -> None:
    assert [n.id for n in tree.path_to_root("context-tests")] == [
        "context-tests",
        "write-tests",
        "ship-update",
    ]


def test_path_to_root_of_root_is_just_the_root(tree: ActionTree) -> None:
    assert [n.id for n in tree.path_to_root("ship-update")] == ["ship-update"]


def test_path_to_root_of_missing_node_is_empty(tree: ActionTree) -> None:
    assert tree.path_to_root("missing") == []


def test_graft_adds_a_child_under_a_parent(tree: ActionTree) -> None:
    child = Action(id="event-tests", label="test events")
    grown = tree.graft("write-tests", child)

    seated = grown.find("event-tests")
    assert seated is not None
    assert seated.parent_id == "write-tests"  # reparented even though we passed None
    assert grown.parent_of("event-tests").id == "write-tests"  # type: ignore[union-attr]


def test_graft_is_pure_and_leaves_the_original_untouched(tree: ActionTree) -> None:
    tree.graft("write-tests", Action(id="event-tests", label="test events"))
    assert tree.find("event-tests") is None  # original is unchanged


def test_graft_under_missing_parent_raises(tree: ActionTree) -> None:
    with pytest.raises(KeyError):
        tree.graft("no-such-parent", Action(id="x", label="x"))


def test_round_trip_through_dict(tree: ActionTree) -> None:
    assert ActionTree.from_dict(tree.to_dict()) == tree


def test_round_trip_through_json(tree: ActionTree) -> None:
    assert ActionTree.from_json(tree.to_json()) == tree


def test_serialised_shape_carries_the_schema_version(tree: ActionTree) -> None:
    assert tree.to_dict()["schema_version"] == ACTION_TREE_SCHEMA_VERSION


def test_from_dict_rejects_an_unknown_schema_version(tree: ActionTree) -> None:
    data = tree.to_dict()
    data["schema_version"] = 999
    with pytest.raises(ValueError, match="unsupported ActionTree schema_version"):
        ActionTree.from_dict(data)


def test_serialised_root_omits_none_parent_and_empty_children() -> None:
    leaf = ActionTree(Action(id="solo", label="solo"))
    root = leaf.to_dict()["root"]
    assert "parent_id" not in root
    assert "children" not in root


class TestInMemoryActionTreeStore:
    def test_satisfies_the_protocol(self) -> None:
        assert isinstance(InMemoryActionTreeStore(), ActionTreeStore)

    def test_load_before_save_is_none(self) -> None:
        assert InMemoryActionTreeStore().load() is None

    def test_save_then_load_round_trips(self, tree: ActionTree) -> None:
        store = InMemoryActionTreeStore()
        store.save(tree)
        assert store.load() == tree

    def test_save_replaces_the_previous_tree(self, tree: ActionTree) -> None:
        store = InMemoryActionTreeStore()
        store.save(tree)
        store.save(ActionTree(Action(id="other", label="other")))
        loaded = store.load()
        assert loaded is not None
        assert loaded.root.id == "other"
