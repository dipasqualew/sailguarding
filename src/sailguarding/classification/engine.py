"""The selector engine — the first :class:`ClassificationStrategy`.

It holds a registry of :class:`SelectorRule`\\ s and classifies an event by evaluating them.
This is the cheap, honest, deterministic floor the SPEC asks for; a model-based strategy comes
later behind the same :class:`ClassificationStrategy` seam.

**Conflict rule (documented, not implicit).** When several selectors match one event:

1. The most **specific** selector wins — highest :attr:`Selector.specificity` (constraints that
   actually narrow, universal wildcards excluded).
2. Ties in specificity break by explicit **priority** (higher wins).
3. If, after 1 and 2, the top rules still bind to *different* actions, the classification is
   **ambiguous**. The engine does **not** guess. It reports ``AMBIGUOUS`` so the matcher routes
   the event to triage — the conservative outcome (a human models it; the agent earns no
   autonomy from a coin-flip), never an arbitrary permissive pick. This is the SPEC's "fail
   toward caution" made concrete at classification time, before any delegation float exists.

Top rules that all name the *same* action are not a conflict: the event simply resolves to it.
"""

from __future__ import annotations

from collections.abc import Iterable

from sailguarding.classification.selector import SelectorRule
from sailguarding.classification.strategy import Classification
from sailguarding.domain import EventRecord


class SelectorClassificationStrategy:
    """A :class:`ClassificationStrategy` backed by an ordered set of selector rules."""

    def __init__(self, rules: Iterable[SelectorRule] = ()) -> None:
        self._rules: list[SelectorRule] = list(rules)

    def register(self, rule: SelectorRule) -> None:
        """Add a rule to the registry. Registration order does not affect the outcome; the
        conflict rule (specificity, then priority) fully determines the winner."""
        self._rules.append(rule)

    @property
    def rules(self) -> tuple[SelectorRule, ...]:
        return tuple(self._rules)

    def classify(self, event: EventRecord) -> Classification:
        matches = [rule for rule in self._rules if rule.selector.matches(event)]
        if not matches:
            return Classification.unmatched()

        best = max((rule.selector.specificity, rule.priority) for rule in matches)
        top = [rule for rule in matches if (rule.selector.specificity, rule.priority) == best]

        action_ids = {rule.action_id for rule in top}
        if len(action_ids) == 1:
            return Classification.matched(next(iter(action_ids)))
        return Classification.ambiguous(tuple(sorted(action_ids)))
