"""The error budget — the second number the delegation float is read against.

A safeguard's signal says *is this control holding right now?*; an :class:`ErrorBudget` says
*how much failure does this region of work still have room for?* The scorer reads both: even when
every safeguard holds, a nearly-spent budget must pull the float toward the human. This task
**defines and resolves** budgets; **spending** them from real outcomes is measurement (task 08),
so ``remaining`` is supplied directly here — later it is derived from a limit minus what evidence
has consumed.

A budget binds to a region exactly as a safeguard does — through the shared :class:`Selector`
predicate over context, plus an **activity-class glob** — so an *activity class · context
selector* is the same predicate machinery tasks 04/06 already use (:class:`BudgetBinding`). What
is new here is
**inheritance**: a budget declared on a parent applies to every descendant that does not declare its
own, and that rule is pinned once in :func:`resolve_budget` rather than rediscovered per feature.

**The inheritance rule, pinned (SPEC open question #4).** The **nearest declared ancestor's budget
applies, unless a node declares its own — which overrides.** Resolution walks from the node up to
the root and returns the first budget that binds; because the node itself is checked first, a leaf's
own budget always wins over anything it would otherwise inherit. Budgets **override**, they do not
compose: a node with its own budget is governed by exactly that one, not by some blend with its
parent's. This is decided here, in one place, and tested parent→leaf (including an explicit
override).

The registry is a pluggable seam with an in-memory default, so a fresh tree + budgets drive tests
with no I/O, mirroring :class:`~sailguarding.safeguards.InMemoryBindingRegistry`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from sailguarding.classification import Selector

if TYPE_CHECKING:
    from sailguarding.tree.tree import ActivityTree

# Bumped whenever the serialised shape of an ErrorBudget changes, so a reader can tell which schema
# produced a stored record.
ERROR_BUDGET_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ErrorBudget:
    """A risk appetite for a region of work: how much of its failure allowance is still unspent.

    :param id: Stable identifier, referenced by a binding and (later) by a decision log entry.
    :param label: Human-readable name for dashboards and audit trails.
    :param remaining: The fraction of the budget still unspent, ``0.0`` (exhausted) to ``1.0``
        (full). The scorer reads this as ``remaining_budget``: a value near ``0`` collapses the
        delegation float toward the human even when every safeguard holds. Task 08 will derive it
        from a limit minus what evidence has consumed; here it is declared directly.
    :param schema_version: The record schema version; defaults to the current one.
    """

    id: str
    label: str
    remaining: float = 1.0
    schema_version: int = field(default=ERROR_BUDGET_SCHEMA_VERSION)

    def __post_init__(self) -> None:
        if not 0.0 <= self.remaining <= 1.0:
            raise ValueError(f"ErrorBudget.remaining must be in [0,1], got {self.remaining!r}")

    def to_dict(self) -> dict[str, Any]:
        """A JSON-compatible dict."""
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "label": self.label,
            "remaining": self.remaining,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ErrorBudget:
        """Rebuild a budget from :meth:`to_dict` output, rejecting an unknown schema version."""
        version = data.get("schema_version", ERROR_BUDGET_SCHEMA_VERSION)
        if version != ERROR_BUDGET_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported ErrorBudget schema_version {version!r}; "
                f"this build reads version {ERROR_BUDGET_SCHEMA_VERSION}"
            )
        return cls(
            id=data["id"],
            label=data["label"],
            remaining=data.get("remaining", 1.0),
            schema_version=version,
        )

    def to_json(self) -> str:
        """Serialise to a canonical, single-line JSON string (sorted keys, tight separators)."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> ErrorBudget:
        """Parse a budget from a JSON string produced by :meth:`to_json`."""
        return cls.from_dict(json.loads(text))


@dataclass(frozen=True)
class BudgetBinding:
    """An :class:`ErrorBudget` bound to the *activity-class · context* region it governs.

    The same binding shape as :class:`~sailguarding.safeguards.SafeguardBinding`, reused verbatim so
    budgets and safeguards do not fork a second predicate language. Only the selector's **context**
    half participates (a binding delimits a region of context, not an event); the **activity** glob
    scopes it to an activity class.

    :param budget: The budget this region is governed by.
    :param selector: The context predicate; its context dimensions must match the resolved context.
    :param activity: An activity-id glob (default ``"*"``, every activity). Governs an activity
        only when this glob matches the activity's id — ``"write-tests"`` or ``"write-*"`` scopes
        it narrower.
    :param priority: Breaks ties between equally specific bindings *at the same node* (higher wins),
        mirroring :class:`~sailguarding.classification.SelectorRule.priority`.
    """

    budget: ErrorBudget
    selector: Selector = field(default_factory=Selector)
    activity: str = "*"
    priority: int = 0

    def matches(self, activity_id: str, context: Mapping[str, Any]) -> bool:
        """True when this binding governs ``activity_id`` running in ``context``.

        Both axes must hold: the ``activity`` glob matches ``activity_id`` and the selector's
        context predicate matches ``context``.
        """
        return fnmatchcase(activity_id, self.activity) and self.selector.matches_context(context)

    @property
    def specificity(self) -> int:
        """How many axes this binding narrows on — the tie-breaker between bindings at one node.

        The selector's context :attr:`~sailguarding.classification.Selector.specificity` plus one if
        the ``activity`` glob is not the bare ``"*"`` wildcard. Mirrors
        :attr:`~sailguarding.safeguards.SafeguardBinding.specificity`.
        """
        return self.selector.specificity + (0 if self.activity == "*" else 1)

    def to_dict(self) -> dict[str, Any]:
        """A JSON-serialisable form; the selector serialises through its own ``to_dict``."""
        return {
            "budget": self.budget.to_dict(),
            "selector": self.selector.to_dict(),
            "activity": self.activity,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BudgetBinding:
        """Rebuild a binding from :meth:`to_dict` output."""
        return cls(
            budget=ErrorBudget.from_dict(data["budget"]),
            selector=Selector.from_dict(data.get("selector", {})),
            activity=data.get("activity", "*"),
            priority=data.get("priority", 0),
        )

    def to_json(self) -> str:
        """Serialise to a canonical, single-line JSON string (sorted keys, tight separators)."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> BudgetBinding:
        """Parse a binding from a JSON string produced by :meth:`to_json`."""
        return cls.from_dict(json.loads(text))


@runtime_checkable
class BudgetRegistry(Protocol):
    """Resolve the single budget binding declared *at* one ``(activity, context)``, if any.

    Deliberately node-local: it answers "does *this* node declare a budget?", not "what does this
    node inherit?". Inheritance across the tree is :func:`resolve_budget`'s job, kept separate so
    the rule lives in exactly one place. A stub returning a fixed binding is a valid registry.
    """

    def resolve_local(self, activity_id: str, context: Mapping[str, Any]) -> BudgetBinding | None:
        """The most-specific budget binding declared at ``(activity_id, context)``, or ``None``."""
        ...


class InMemoryBudgetRegistry:
    """A :class:`BudgetRegistry` backed by an in-process list of bindings.

    The injectable default: nothing shared between instances, so a case registers a fresh set of
    budgets and reads back exactly what each node declares.
    """

    def __init__(self, bindings: Iterable[BudgetBinding] = ()) -> None:
        self._bindings: list[BudgetBinding] = list(bindings)

    def register(self, binding: BudgetBinding) -> None:
        """Add a binding. Registration order affects only the final, already-broken tie."""
        self._bindings.append(binding)

    @property
    def bindings(self) -> tuple[BudgetBinding, ...]:
        return tuple(self._bindings)

    def resolve_local(self, activity_id: str, context: Mapping[str, Any]) -> BudgetBinding | None:
        """The most-specific budget binding declared at this exact ``(activity_id, context)``.

        A node may be covered by several matching bindings; the most specific wins, breaking ties by
        ``priority`` (higher wins) and then registration order (first registered wins), so the
        outcome is deterministic — the same resolution the safeguard registry uses.
        """
        winner: BudgetBinding | None = None
        for binding in self._bindings:
            if not binding.matches(activity_id, context):
                continue
            if winner is None or _outranks(binding, winner):
                winner = binding
        return winner


def resolve_budget(
    tree: ActivityTree,
    activity_id: str,
    context: Mapping[str, Any],
    registry: BudgetRegistry,
) -> ErrorBudget | None:
    """Resolve the budget governing ``activity_id`` in ``context``, applying inheritance.

    **The pinned rule:** walk from the node up to the root and return the first budget that binds.
    Because the node itself is checked before its ancestors, a node's own declaration **overrides**
    anything it would otherwise inherit; a node with no declaration inherits its **nearest declared
    ancestor's** budget. Returns ``None`` when neither the node nor any ancestor declares one — the
    caller decides the default (the scorer treats a missing budget as full headroom).

    Budgets override, they do not compose: exactly one budget governs a node, never a blend.
    """
    for node in tree.path_to_root(activity_id):
        binding = registry.resolve_local(node.id, context)
        if binding is not None:
            return binding.budget
    return None


def _outranks(candidate: BudgetBinding, incumbent: BudgetBinding) -> bool:
    """True when ``candidate`` should replace ``incumbent`` at the same node.

    Strictly-greater on ``(specificity, priority)``; an exact tie keeps the incumbent, which is the
    earlier-registered binding (first-registered wins).
    """
    return (candidate.specificity, candidate.priority) > (
        incumbent.specificity,
        incumbent.priority,
    )
