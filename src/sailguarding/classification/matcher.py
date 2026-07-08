"""The matcher — resolves each event to an activity and fills ``activity_id``.

The matcher is the orchestration layer over a :class:`ClassificationStrategy`: it runs the
injected strategy, and on a resolved match returns the event with ``activity_id`` filled. On an
unresolved event (unmatched *or* ambiguous) it leaves ``activity_id`` ``None`` and routes the event
to the :class:`TriageQueue`, so nothing is silently dropped.

The strategy is injected, never hard-wired — swap the selector engine for a stub, or later for a
model strategy, without touching this code.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from sailguarding.classification.strategy import ClassificationStrategy
from sailguarding.classification.triage import TriageEntry, TriageQueue
from sailguarding.domain import EventRecord


class Matcher:
    """Resolve events to activities via a strategy, sending the unresolved to triage."""

    def __init__(
        self,
        strategy: ClassificationStrategy,
        triage: TriageQueue | None = None,
    ) -> None:
        self._strategy = strategy
        self._triage = triage if triage is not None else TriageQueue()

    @property
    def triage(self) -> TriageQueue:
        return self._triage

    def classify(self, event: EventRecord) -> EventRecord:
        """Return ``event`` with ``activity_id`` filled if resolved; otherwise triage it and
        return it unchanged (``activity_id`` still ``None``)."""
        result = self._strategy.classify(event)
        if result.activity_id is not None:
            return replace(event, activity_id=result.activity_id)

        self._triage.add(
            TriageEntry(event=event, reason=result.outcome, candidates=result.candidates)
        )
        return event

    def classify_all(self, events: Iterable[EventRecord]) -> list[EventRecord]:
        """Classify a batch, preserving order. Unresolved events accumulate in the triage queue."""
        return [self.classify(event) for event in events]
