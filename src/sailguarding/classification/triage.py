"""The triage queue — where unresolved events go to be modelled bottom-up.

Events matching no selector, or matching ambiguously, are **not silently dropped**: they land
here so a human can inspect them and author a new action + selector. That is the bottom-up
modelling loop the SPEC calls for — the system learns new actions from the events it could not
yet name, instead of pretending it saw nothing.

This is an in-memory collector, mirroring :class:`InMemoryStorage`: no git, no filesystem, no
shared state, so tests inject a fresh one per case. A durable triage sink can implement the same
shape later.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from sailguarding.classification.strategy import Outcome
from sailguarding.domain import EventRecord


@dataclass(frozen=True)
class TriageEntry:
    """One event that could not be resolved, with why.

    :param event: The unresolved event, verbatim (its ``action_id`` is still ``None``).
    :param reason: ``UNMATCHED`` (no selector matched) or ``AMBIGUOUS`` (selectors disagreed).
    :param candidates: The tied action ids when ``reason`` is ``AMBIGUOUS``; empty otherwise.
    """

    event: EventRecord
    reason: Outcome
    candidates: tuple[str, ...] = field(default_factory=tuple)


class TriageQueue:
    """An append-and-query collector of :class:`TriageEntry`\\ s, in arrival order."""

    def __init__(self) -> None:
        self._entries: list[TriageEntry] = []

    def add(self, entry: TriageEntry) -> None:
        self._entries.append(entry)

    def pending(self) -> tuple[TriageEntry, ...]:
        """Every entry awaiting a human, in the order it arrived."""
        return tuple(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[TriageEntry]:
        return iter(self._entries)
