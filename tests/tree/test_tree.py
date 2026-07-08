"""Unit tests for :class:`ActivityTree`: navigation, growth, and round-trip serialisation."""

from __future__ import annotations

import pytest

from sailguarding.domain import Activity
from sailguarding.tree import (
    ACTIVITY_TREE_SCHEMA_VERSION,
    ActivityTree,
    ActivityTreeStore,
    InMemoryActivityTreeStore,
)


@pytest.fixture
def tree() -> ActivityTree:
    """The SPEC worked example as a tree.

    ship-update (root)
      ├─ write-tests
      │    └─ context-tests (leaf)
      └─ update-docs (leaf)
    """
    context_tests = Activity(id="context-tests", label="test context", parent_id="write-tests")
    write_tests = Activity(
        id="write-tests",
        label="write the tests",
        parent_id="ship-update",
        children=(context_tests,),
    )
    update_docs = Activity(id="update-docs", label="update the docs", parent_id="ship-update")
    root = Activity(id="ship-update", label="ship the update", children=(write_tests, update_docs))
    return ActivityTree(root)


def test_find_and_walk_delegate_to_the_root(tree: ActivityTree) -> None:
    assert [n.id for n in tree.walk()] == [
        "ship-update",
        "write-tests",
        "context-tests",
        "update-docs",
    ]
    assert tree.find("context-tests") is not None
    assert tree.find("nope") is None


def test_parent_of(tree: ActivityTree) -> None:
    assert tree.parent_of("context-tests").id == "write-tests"  # type: ignore[union-attr]
    assert tree.parent_of("write-tests").id == "ship-update"  # type: ignore[union-attr]
    assert tree.parent_of("ship-update") is None  # root has no parent
    assert tree.parent_of("missing") is None


def test_path_to_root_is_node_first_then_ancestors(tree: ActivityTree) -> None:
    assert [n.id for n in tree.path_to_root("context-tests")] == [
        "context-tests",
        "write-tests",
        "ship-update",
    ]


def test_path_to_root_of_root_is_just_the_root(tree: ActivityTree) -> None:
    assert [n.id for n in tree.path_to_root("ship-update")] == ["ship-update"]


def test_path_to_root_of_missing_node_is_empty(tree: ActivityTree) -> None:
    assert tree.path_to_root("missing") == []


def test_graft_adds_a_child_under_a_parent(tree: ActivityTree) -> None:
    child = Activity(id="event-tests", label="test events")
    grown = tree.graft("write-tests", child)

    seated = grown.find("event-tests")
    assert seated is not None
    assert seated.parent_id == "write-tests"  # reparented even though we passed None
    assert grown.parent_of("event-tests").id == "write-tests"  # type: ignore[union-attr]


def test_graft_is_pure_and_leaves_the_original_untouched(tree: ActivityTree) -> None:
    tree.graft("write-tests", Activity(id="event-tests", label="test events"))
    assert tree.find("event-tests") is None  # original is unchanged


def test_graft_under_missing_parent_raises(tree: ActivityTree) -> None:
    with pytest.raises(KeyError):
        tree.graft("no-such-parent", Activity(id="x", label="x"))


def test_round_trip_through_dict(tree: ActivityTree) -> None:
    assert ActivityTree.from_dict(tree.to_dict()) == tree


def test_round_trip_through_json(tree: ActivityTree) -> None:
    assert ActivityTree.from_json(tree.to_json()) == tree


def test_serialised_shape_carries_the_schema_version(tree: ActivityTree) -> None:
    assert tree.to_dict()["schema_version"] == ACTIVITY_TREE_SCHEMA_VERSION


def test_from_dict_rejects_an_unknown_schema_version(tree: ActivityTree) -> None:
    data = tree.to_dict()
    data["schema_version"] = 999
    with pytest.raises(ValueError, match="unsupported ActivityTree schema_version"):
        ActivityTree.from_dict(data)


def test_serialised_root_omits_none_parent_and_empty_children() -> None:
    leaf = ActivityTree(Activity(id="solo", label="solo"))
    root = leaf.to_dict()["root"]
    assert "parent_id" not in root
    assert "children" not in root


class TestInMemoryActivityTreeStore:
    def test_satisfies_the_protocol(self) -> None:
        assert isinstance(InMemoryActivityTreeStore(), ActivityTreeStore)

    def test_load_before_save_is_none(self) -> None:
        assert InMemoryActivityTreeStore().load() is None

    def test_save_then_load_round_trips(self, tree: ActivityTree) -> None:
        store = InMemoryActivityTreeStore()
        store.save(tree)
        assert store.load() == tree

    def test_save_replaces_the_previous_tree(self, tree: ActivityTree) -> None:
        store = InMemoryActivityTreeStore()
        store.save(tree)
        store.save(ActivityTree(Activity(id="other", label="other")))
        loaded = store.load()
        assert loaded is not None
        assert loaded.root.id == "other"
