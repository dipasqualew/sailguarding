"""The pluggable storage seam every sink implements.

Observations have to land somewhere, but *where* is a strategy choice, not a fixed
backend: the engine starts with zero infrastructure (an in-memory sink) and grows into a
real store later. :class:`StorageStrategy` is the minimal, injectable contract that task 03
(the sensor) writes through and later tasks read from.

Two SPEC constraints shape this seam:

- **The event log is not the metrics.** This contract is the raw *event log* only. Derived
  safeguard metrics get their own, separate sink later; do not add metric queries here.
- **Sharding avoids merges.** A sink writes one append-only stream per
  ``{session_id}/{date}`` shard so nothing is shared and nothing has to merge.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Protocol, runtime_checkable

from sailguarding.domain import EventRecord


@runtime_checkable
class StorageStrategy(Protocol):
    """Append-only sink for :class:`EventRecord`s with three read paths.

    Implementations must round-trip: appending a record and reading it back yields an
    equal :class:`EventRecord`. Append is atomic per record — a partial append never
    leaves a half-written record visible to a reader.
    """

    def append(self, record: EventRecord) -> None:
        """Append a single record. Atomic: the record is either fully stored or not."""
        ...

    def append_many(self, records: Iterable[EventRecord]) -> None:
        """Append several records. Atomic as a batch: all land or none do."""
        ...

    def read_session(self, session_id: str) -> list[EventRecord]:
        """Every record for one session, across all days, in append order."""
        ...

    def read_day(self, day: date) -> list[EventRecord]:
        """Every record whose (UTC) timestamp falls on ``day``, across all sessions."""
        ...

    def scan(self) -> list[EventRecord]:
        """Every record in the store."""
        ...
