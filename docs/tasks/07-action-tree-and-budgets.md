# 07 — Action tree & error budgets

**Status:** done
**Depends on:** 01, 04, 06

## Context

The `Action` type (task 01) is the recursive unit — root or leaf, one self-similar node with
children. So far it exists but nothing *builds* a tree or attaches governance to it. This task does
both: it seeds the tree **bottom-up from observed work**, and it hangs the second number the score is
read against — the **error budget** — off the tree.

Two SPEC commitments shape it:

- **Curate, don't author from a blank page.** The tree grows from what agents actually did: the
  triage queue (task 04) already collects events that matched no action. Seeding the tree means
  turning those into named actions + selectors, not inventing a taxonomy up front.
- **Fix inheritance once, up front.** A budget attaches to an **action-class × context selector**, and
  budgets inherit down the tree. Whether a leaf's budget *overrides* its parent's or *composes* with
  it (open question #4) must be decided once, documented, and enforced — not rediscovered per feature.

## Scope

- **Tree store / builder:** persist and reload an `Action` tree, and a path from a `TriageEntry`
  (task 04) to a new action + selector, so the tree is seeded from real events. Versioned,
  serializable, round-trip tested.
- **`ErrorBudget`:** a risk appetite bound to an action-class × context selector, resolvable for any
  node in the tree.
- **Inheritance semantics, pinned:** decide and document the rule (recommended default: the nearest
  declared ancestor's budget applies unless a node declares its own, which overrides). Whatever the
  choice, it is defined in one place and tested parent→leaf.

## Out of scope

- **Spending the budget from evidence** (task 08) — this task defines and resolves budgets; consuming
  them against real outcomes comes with measurement.
- **Behaviour bands and enforcement** (task 10).
- **Cross-context rollup** (open question #5).

## Acceptance criteria

- An `Action` tree can be seeded from triage entries and is serializable/round-trip tested.
- An `ErrorBudget` binds to an action-class × context selector and is resolvable for a given node.
- The inheritance/override rule is pinned, documented, and tested across at least one parent→leaf
  chain (including an explicit override).
- Stores are injected with in-memory defaults; a fresh tree + budgets drive tests with no I/O.

## Demo

An **action-tree panel** on the dashboard showing the demo action within its tree. Set a budget on a
parent node and watch a leaf **inherit** it (and an explicit leaf override win). The remaining budget
the scorer reads for the demo action is the *resolved* budget from this chain — so the tree visibly
drives the `remaining_budget` input to the delegation float.

## Notes

- Reuse the `Selector` binding shape from tasks 04/06 for budgets; an action class × context selector
  is the same predicate machinery.
- Keep the tree domain-agnostic: "ship a regulation-compliant update" decomposes exactly as "buy a
  sofa" does.
