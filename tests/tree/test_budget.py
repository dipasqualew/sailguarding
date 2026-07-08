"""Unit tests for error budgets: the type, node-local resolution, and tree inheritance.

The inheritance/override rule is the load-bearing decision (SPEC open question #4), so it is tested
across a parent→leaf chain, including an explicit leaf override.
"""

from __future__ import annotations

import pytest

from sailguarding.classification import Selector
from sailguarding.domain import Activity, Context
from sailguarding.tree import (
    ERROR_BUDGET_SCHEMA_VERSION,
    ActivityTree,
    BudgetBinding,
    BudgetRegistry,
    ErrorBudget,
    InMemoryBudgetRegistry,
    resolve_budget,
)

CHECKOUT = Context(repo="checkout", environment="prod")


@pytest.fixture
def tree() -> ActivityTree:
    """ship-update (root) → write-tests → context-tests (leaf)."""
    context_tests = Activity(id="context-tests", label="test context", parent_id="write-tests")
    write_tests = Activity(
        id="write-tests",
        label="write the tests",
        parent_id="ship-update",
        children=(context_tests,),
    )
    return ActivityTree(
        Activity(id="ship-update", label="ship the update", children=(write_tests,))
    )


def _binding(
    bid: str,
    remaining: float,
    *,
    context: dict[str, str] | None = None,
    activity: str = "*",
    priority: int = 0,
) -> BudgetBinding:
    return BudgetBinding(
        budget=ErrorBudget(id=bid, label=bid, remaining=remaining),
        selector=Selector(context=context or {"repo": "checkout"}),
        activity=activity,
        priority=priority,
    )


# --- ErrorBudget: construction and round-trip ---------------------------------------------------


def test_error_budget_round_trips_through_json() -> None:
    budget = ErrorBudget(id="ship", label="Ship budget", remaining=0.4)
    assert ErrorBudget.from_json(budget.to_json()) == budget


def test_error_budget_carries_the_schema_version() -> None:
    assert ErrorBudget(id="b", label="b").to_dict()["schema_version"] == ERROR_BUDGET_SCHEMA_VERSION


def test_error_budget_from_dict_rejects_unknown_schema_version() -> None:
    data = ErrorBudget(id="b", label="b").to_dict()
    data["schema_version"] = 999
    with pytest.raises(ValueError, match="unsupported ErrorBudget schema_version"):
        ErrorBudget.from_dict(data)


@pytest.mark.parametrize("remaining", [-0.01, 1.01, 2.0])
def test_error_budget_remaining_must_be_a_fraction(remaining: float) -> None:
    with pytest.raises(ValueError, match=r"remaining must be in \[0,1\]"):
        ErrorBudget(id="b", label="b", remaining=remaining)


# --- BudgetBinding: same predicate machinery as safeguards --------------------------------------


def test_binding_round_trips_through_json() -> None:
    binding = _binding("ship", 0.5, activity="write-tests")
    assert BudgetBinding.from_json(binding.to_json()) == binding


def test_binding_matches_on_both_action_and_context() -> None:
    binding = _binding("ship", 0.5, activity="write-*")
    assert binding.matches("write-tests", CHECKOUT)
    assert not binding.matches("deploy", CHECKOUT)  # activity glob misses
    assert not binding.matches("write-tests", Context(repo="billing"))  # context misses


def test_binding_specificity_counts_context_and_action() -> None:
    assert _binding("b", 0.5, context={"repo": "checkout"}, activity="*").specificity == 1
    assert _binding("b", 0.5, context={"repo": "checkout"}, activity="write-tests").specificity == 2


# --- Node-local resolution ----------------------------------------------------------------------


def test_registry_satisfies_the_protocol() -> None:
    assert isinstance(InMemoryBudgetRegistry(), BudgetRegistry)


def test_resolve_local_returns_none_when_nothing_binds() -> None:
    registry = InMemoryBudgetRegistry([_binding("ship", 0.5, context={"repo": "billing"})])
    assert registry.resolve_local("write-tests", CHECKOUT) is None


def test_resolve_local_prefers_the_more_specific_binding() -> None:
    broad = _binding("broad", 0.9, activity="*")
    narrow = _binding("narrow", 0.2, activity="write-tests")
    registry = InMemoryBudgetRegistry([broad, narrow])
    resolved = registry.resolve_local("write-tests", CHECKOUT)
    assert resolved is narrow


def test_resolve_local_breaks_specificity_ties_by_priority() -> None:
    low = _binding("low", 0.9, priority=0)
    high = _binding("high", 0.2, priority=5)
    registry = InMemoryBudgetRegistry([low, high])
    assert registry.resolve_local("write-tests", CHECKOUT) is high


# --- Inheritance: the pinned rule, parent → leaf ------------------------------------------------


def test_leaf_inherits_the_nearest_declared_ancestors_budget(tree: ActivityTree) -> None:
    # Budget declared only on the root; the deep leaf inherits it.
    registry = InMemoryBudgetRegistry([_binding("ship", 0.4, activity="ship-update")])
    resolved = resolve_budget(tree, "context-tests", CHECKOUT, registry)
    assert resolved is not None
    assert resolved.id == "ship"
    assert resolved.remaining == 0.4


def test_nearest_ancestor_wins_over_a_further_one(tree: ActivityTree) -> None:
    registry = InMemoryBudgetRegistry(
        [
            _binding("root", 0.4, activity="ship-update"),
            _binding("mid", 0.6, activity="write-tests"),  # nearer to the leaf
        ]
    )
    resolved = resolve_budget(tree, "context-tests", CHECKOUT, registry)
    assert resolved is not None
    assert resolved.id == "mid"


def test_a_nodes_own_budget_overrides_what_it_would_inherit(tree: ActivityTree) -> None:
    registry = InMemoryBudgetRegistry(
        [
            _binding("root", 0.4, activity="ship-update"),
            _binding("leaf-override", 0.1, activity="context-tests"),
        ]
    )
    resolved = resolve_budget(tree, "context-tests", CHECKOUT, registry)
    assert resolved is not None
    assert resolved.id == "leaf-override"
    assert resolved.remaining == 0.1


def test_no_budget_anywhere_resolves_to_none(tree: ActivityTree) -> None:
    assert resolve_budget(tree, "context-tests", CHECKOUT, InMemoryBudgetRegistry()) is None


def test_inheritance_does_not_cross_a_context_boundary(tree: ActivityTree) -> None:
    # The root's budget only binds in repo=checkout; resolving in another repo inherits nothing.
    registry = InMemoryBudgetRegistry([_binding("ship", 0.4, activity="ship-update")])
    assert resolve_budget(tree, "context-tests", Context(repo="billing"), registry) is None
