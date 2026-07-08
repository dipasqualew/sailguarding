"""The metrics sink — a pluggable append/query seam for :class:`Evidence`, kept apart from the log.

This is *not* the event-log storage of task 02, and deliberately so. Git is a fine append-only log
and a terrible time-series database; derived safeguard metrics are a separate concern with a
separate lifecycle (joined to activities after the fact, summarised over time), so they get their
own sink. This module never touches :class:`~sailguarding.storage.StorageStrategy` and that seam
never grows a metric query — the two stay distinct, as the SPEC's architecture section requires.

The read path is where the "never conflate health and efficacy" rule is enforced *by the type*:
:meth:`MetricsSink.series` **requires** a :class:`~sailguarding.safeguards.Measurement`, so there is
no API path that hands back a safeguard's evidence without saying which kind was asked for. A caller
cannot accidentally read a health proxy where it wanted efficacy — it must name the series.

The sink is a :class:`Protocol` with an injectable in-memory default, mirroring the storage and
registry seams, so tests ingest and read back with no I/O.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from sailguarding.measurement.evidence import Evidence
from sailguarding.safeguards import Measurement


@runtime_checkable
class MetricsSink(Protocol):
    """Append-only sink for :class:`Evidence` whose per-safeguard read path is kind-scoped.

    Implementations must round-trip: appending a record and reading it back yields an equal
    :class:`Evidence`. The only per-safeguard query, :meth:`series`, takes a
    :class:`~sailguarding.safeguards.Measurement` and returns **only** that kind — the platform
    never lets one kind be read where the other was asked for.
    """

    def append(self, evidence: Evidence) -> None:
        """Append a single evidence record."""
        ...

    def append_many(self, records: Iterable[Evidence]) -> None:
        """Append several evidence records, in order."""
        ...

    def series(self, safeguard_id: str, measures: Measurement) -> list[Evidence]:
        """One safeguard's evidence of exactly ``measures``, oldest measurement first.

        Requiring ``measures`` is the enforcement of the never-conflate rule: a health series and an
        efficacy series are separate queries, and neither can return the other's records.
        """
        ...

    def scan(self) -> list[Evidence]:
        """Every evidence record in the sink, in append order."""
        ...


class InMemoryMetricsSink:
    """A :class:`MetricsSink` backed by an in-process list.

    The injectable default: no git, no filesystem, no shared state, so tests inject a fresh one per
    case. :meth:`series` returns evidence sorted by timestamp (oldest first, ties broken by
    insertion order) so a derived signal or sparkline reads the same regardless of ingestion order.
    """

    def __init__(self, records: Iterable[Evidence] = ()) -> None:
        self._records: list[Evidence] = list(records)

    def append(self, evidence: Evidence) -> None:
        self._records.append(evidence)

    def append_many(self, records: Iterable[Evidence]) -> None:
        self._records.extend(records)

    def series(self, safeguard_id: str, measures: Measurement) -> list[Evidence]:
        matches = [
            record
            for record in self._records
            if record.safeguard_id == safeguard_id and record.measures is measures
        ]
        # Python's sort is stable, so equal timestamps keep their insertion order — a deterministic
        # tie-break without a secondary key.
        return sorted(matches, key=lambda record: record.timestamp)

    def scan(self) -> list[Evidence]:
        return list(self._records)
