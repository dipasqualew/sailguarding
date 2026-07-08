"""The pluggable seam that turns an observed event into an activity.

A raw tool event (``Edit(foo.test.ts)``) is not an *activity* — "writing tests" is.
Bridging that gap is **classification**, and per the SPEC it is part of the safeguarding
calculus, not plumbing: you cannot guard an activity you failed to recognise. So it is a
strategy choice, not a fixed rule.

:class:`ClassificationStrategy` is the minimal contract. The deterministic selector engine
(:mod:`sailguarding.classification.engine`) is the first implementation; a later model-based
strategy (ML, small model, LLM) must satisfy the *same* interface without changing it. A
strategy answers one question — ``event → activity_id | unmatched`` — and nothing else. Filling
``activity_id`` on the record and routing the unmatched to triage is the matcher's job, not the
strategy's.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from sailguarding.domain import EventRecord


class Outcome(enum.Enum):
    """How a strategy resolved an event.

    ``MATCHED`` carries an ``activity_id``. ``UNMATCHED`` means no rule recognised the event.
    ``AMBIGUOUS`` means rules matched but disagreed on the activity and could not be reconciled
    by the conflict rule — the honest "I don't know", distinct from "nothing matched" so a
    human triaging the event can tell the two apart.
    """

    MATCHED = "matched"
    UNMATCHED = "unmatched"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class Classification:
    """The result of classifying one event.

    :param outcome: Which of the three :class:`Outcome` cases occurred.
    :param activity_id: The resolved activity when ``outcome`` is ``MATCHED``; ``None`` otherwise.
    :param candidates: The tied activity ids when ``outcome`` is ``AMBIGUOUS``; empty otherwise.
        Recorded so a human triaging the event sees exactly which activities collided.
    """

    outcome: Outcome
    activity_id: str | None = None
    candidates: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def matched(cls, activity_id: str) -> Classification:
        return cls(Outcome.MATCHED, activity_id=activity_id)

    @classmethod
    def unmatched(cls) -> Classification:
        return cls(Outcome.UNMATCHED)

    @classmethod
    def ambiguous(cls, candidates: tuple[str, ...]) -> Classification:
        return cls(Outcome.AMBIGUOUS, candidates=tuple(candidates))

    @property
    def is_resolved(self) -> bool:
        """True only when the event resolved to a single activity."""
        return self.activity_id is not None


@runtime_checkable
class ClassificationStrategy(Protocol):
    """Resolve an :class:`EventRecord` to an activity, or report it unresolved.

    The whole contract is one method. A stub returning a fixed :class:`Classification` is a
    valid strategy, which is what lets tests swap the selector engine out.
    """

    def classify(self, event: EventRecord) -> Classification:
        """Return the classification for ``event``. Must not mutate ``event``."""
        ...
