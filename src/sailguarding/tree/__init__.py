"""The action tree and its error budgets — governance hung off the recursive unit of work.

Task 01 gave the recursive :class:`~sailguarding.domain.Action`; this package makes a *tree* of them
into something the engine can build, persist, navigate, and govern:

- :class:`ActionTree` wraps a root action with up-tree navigation (:meth:`ActionTree.path_to_root`),
  growth (:meth:`ActionTree.graft`), and versioned round-trip serialisation, with an injectable
  :class:`ActionTreeStore` (:class:`InMemoryActionTreeStore` by default).
- The tree is seeded **bottom-up from real events**: :func:`seed_action` turns a triaged
  event (task 04) into a named :class:`~sailguarding.domain.Action` plus the
  :class:`~sailguarding.classification.SelectorRule` that recognises it.
- An :class:`ErrorBudget` binds to an *action-class · context* region (:class:`BudgetBinding`,
  resolved node-locally by :class:`InMemoryBudgetRegistry`) and **inherits down the tree** by the
  rule pinned in :func:`resolve_budget`: the nearest declared ancestor's budget applies unless a
  node declares its own, which overrides.

The resolved budget is the ``remaining_budget`` the scorer (task 05) reads — so the tree visibly
drives the delegation float. Spending the budget from evidence is measurement (task 08).
"""

from sailguarding.tree.budget import (
    ERROR_BUDGET_SCHEMA_VERSION,
    BudgetBinding,
    BudgetRegistry,
    ErrorBudget,
    InMemoryBudgetRegistry,
    resolve_budget,
)
from sailguarding.tree.seed import (
    SeededAction,
    seed_action,
    seeded_rules,
    selector_for_event,
)
from sailguarding.tree.tree import (
    ACTION_TREE_SCHEMA_VERSION,
    ActionTree,
    ActionTreeStore,
    InMemoryActionTreeStore,
)

__all__ = [
    "ACTION_TREE_SCHEMA_VERSION",
    "ERROR_BUDGET_SCHEMA_VERSION",
    "ActionTree",
    "ActionTreeStore",
    "BudgetBinding",
    "BudgetRegistry",
    "ErrorBudget",
    "InMemoryActionTreeStore",
    "InMemoryBudgetRegistry",
    "SeededAction",
    "resolve_budget",
    "seed_action",
    "seeded_rules",
    "selector_for_event",
]
