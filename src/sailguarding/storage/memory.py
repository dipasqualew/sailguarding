"""An in-memory sink implementing :class:`StorageStrategy`.

This is the injectable default for unit tests elsewhere: no git, no filesystem, no global
state. It keeps records in a plain list and answers reads by filtering, so its ordering and
round-trip semantics match the branch sink's without any I/O.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date

from sailguarding.domain import EventRecord


class InMemoryStorage:
    """A :class:`StorageStrategy` backed by an in-process list.

    Records are returned in the order they were appended. Nothing is shared with any other
    instance, so tests can inject a fresh one per case.
    """

    def __init__(self) -> None:
        self._records: list[EventRecord] = []

    def append(self, record: EventRecord) -> None:
        self._records.append(record)

    def append_many(self, records: Iterable[EventRecord]) -> None:
        self._records.extend(records)

    def read_session(self, session_id: str) -> list[EventRecord]:
        return [r for r in self._records if r.session_id == session_id]

    def read_day(self, day: date) -> list[EventRecord]:
        return [r for r in self._records if r.timestamp.astimezone(UTC).date() == day]

    def scan(self) -> list[EventRecord]:
        return list(self._records)
