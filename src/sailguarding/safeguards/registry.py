"""The binding registry — which safeguards govern this ``(activity, context)``?

This answers the question task 09 will build a feature vector from: given an activity running in a
context, which safeguards must hold for it to be delegable? It evaluates every bound selector and
returns the ones that match.

**Overlap is not a conflict — it is the point.** Classification resolves an event to *one* activity
and treats disagreement as ambiguity (route to triage). Governance is the opposite: an activity is
routinely governed by *several distinct* safeguards at once (blast radius **and** no-flaky-tests),
and the registry returns the **union** of them. A second, third, fourth safeguard matching is
exactly what a region of context is meant to accumulate.

**Where specificity applies: deduping the *same* safeguard.** The only genuine overlap is one
safeguard bound more than once to regions that both match — e.g. a broad ``repo=checkout`` binding
and a narrow ``repo=checkout, environment=prod`` binding of the same control. Counting it twice
would let a scoring function see a safeguard's ceiling twice. So the registry keeps **one binding
per safeguard id**, choosing the **most specific** (highest :attr:`SafeguardBinding.specificity`),
breaking ties by **priority** (higher wins), and — if still tied — by **registration order** (first
registered wins, so the outcome is deterministic). This mirrors the classifier's specificity → then
priority handling; it just resolves *which binding of a safeguard* rather than *which activity*.

The registry is a pluggable seam: :class:`BindingRegistry` is the minimal contract and
:class:`InMemoryBindingRegistry` is the injectable default, so a test drives governance with a stub
set of bindings and no real risk model.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol, runtime_checkable

from sailguarding.safeguards.binding import SafeguardBinding


@runtime_checkable
class BindingRegistry(Protocol):
    """Resolve the safeguards that govern an ``(activity, context)``.

    The whole contract is one method. A stub returning a fixed list is a valid registry, which is
    what lets downstream code (feature-vector assembly, the scorer) run without a real risk model.
    """

    def resolve(self, activity_id: str, context: Mapping[str, Any]) -> list[SafeguardBinding]:
        """The bindings governing ``activity_id`` in ``context``, one per safeguard id."""
        ...


class InMemoryBindingRegistry:
    """A :class:`BindingRegistry` backed by an in-process list of bindings.

    The injectable default: nothing shared between instances, so a case registers a fresh set and
    reads back exactly which safeguards reach the scorer.
    """

    def __init__(self, bindings: Iterable[SafeguardBinding] = ()) -> None:
        self._bindings: list[SafeguardBinding] = list(bindings)

    def register(self, binding: SafeguardBinding) -> None:
        """Add a binding. Registration order affects only the final, already-broken tie."""
        self._bindings.append(binding)

    @property
    def bindings(self) -> tuple[SafeguardBinding, ...]:
        return tuple(self._bindings)

    def resolve(self, activity_id: str, context: Mapping[str, Any]) -> list[SafeguardBinding]:
        """The governing bindings, deduped to the most specific one per safeguard id.

        Returned in first-appearance order of each safeguard, so the output is stable and readable.
        """
        winners: dict[str, SafeguardBinding] = {}
        for binding in self._bindings:
            if not binding.matches(activity_id, context):
                continue
            sid = binding.safeguard.id
            incumbent = winners.get(sid)
            if incumbent is None or _outranks(binding, incumbent):
                winners[sid] = binding
        return list(winners.values())


def _outranks(candidate: SafeguardBinding, incumbent: SafeguardBinding) -> bool:
    """True when ``candidate`` should replace ``incumbent`` for the same safeguard id.

    Strictly-greater on ``(specificity, priority)``; an exact tie keeps the incumbent, which is the
    earlier-registered binding (first-registered wins).
    """
    return (candidate.specificity, candidate.priority) > (
        incumbent.specificity,
        incumbent.priority,
    )
