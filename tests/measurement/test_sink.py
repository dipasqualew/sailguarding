"""The metrics sink: round-trip, chronological series, and the never-conflate read path.

The sink is a separate seam from the event-log storage of task 02 — nothing here touches
``StorageStrategy`` — and its per-safeguard read path is kind-scoped, so a health series and an
efficacy series are always distinct.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sailguarding.measurement import Evidence, InMemoryMetricsSink, MetricsSink
from sailguarding.safeguards import Measurement
from sailguarding.storage import StorageStrategy


def _at(minute: int) -> datetime:
    return datetime(2026, 7, 5, 12, minute, tzinfo=UTC)


def test_append_then_scan_returns_equal_record(
    evidence_factory: Callable[..., Evidence],
) -> None:
    sink = InMemoryMetricsSink()
    e = evidence_factory()
    sink.append(e)
    assert sink.scan() == [e]


def test_append_many_extends_in_order(evidence_factory: Callable[..., Evidence]) -> None:
    sink = InMemoryMetricsSink()
    first = evidence_factory(value=0.01, timestamp=_at(1))
    second = evidence_factory(value=0.02, timestamp=_at(2))
    sink.append_many([first, second])
    assert sink.scan() == [first, second]


def test_series_filters_by_safeguard_and_kind(
    evidence_factory: Callable[..., Evidence],
) -> None:
    sink = InMemoryMetricsSink()
    health = evidence_factory(safeguard_id="no-flaky-tests", measures=Measurement.HEALTH)
    efficacy = evidence_factory(safeguard_id="no-flaky-tests", measures=Measurement.EFFICACY)
    other = evidence_factory(safeguard_id="impact", measures=Measurement.HEALTH)
    sink.append_many([health, efficacy, other])

    assert sink.series("no-flaky-tests", Measurement.HEALTH) == [health]
    assert sink.series("no-flaky-tests", Measurement.EFFICACY) == [efficacy]
    assert sink.series("impact", Measurement.HEALTH) == [other]


def test_series_never_returns_the_other_kind(
    evidence_factory: Callable[..., Evidence],
) -> None:
    # The load-bearing guarantee: asking for one kind never yields a record of the other.
    sink = InMemoryMetricsSink()
    sink.append(evidence_factory(measures=Measurement.HEALTH))
    assert sink.series("no-flaky-tests", Measurement.EFFICACY) == []


def test_series_is_chronological_regardless_of_ingestion_order(
    evidence_factory: Callable[..., Evidence],
) -> None:
    sink = InMemoryMetricsSink()
    later = evidence_factory(value=0.03, timestamp=_at(5))
    earlier = evidence_factory(value=0.01, timestamp=_at(1))
    middle = evidence_factory(value=0.02, timestamp=_at(3))
    # Ingested out of order; the series comes back oldest-first.
    sink.append_many([later, earlier, middle])
    values = [e.value for e in sink.series("no-flaky-tests", Measurement.HEALTH)]
    assert values == [0.01, 0.02, 0.03]


def test_series_breaks_timestamp_ties_by_insertion_order(
    evidence_factory: Callable[..., Evidence],
) -> None:
    sink = InMemoryMetricsSink()
    first = evidence_factory(value=0.01, timestamp=_at(1))
    second = evidence_factory(value=0.02, timestamp=_at(1))  # same instant
    sink.append_many([first, second])
    assert sink.series("no-flaky-tests", Measurement.HEALTH) == [first, second]


def test_missing_safeguard_is_empty_series(evidence_factory: Callable[..., Evidence]) -> None:
    sink = InMemoryMetricsSink()
    sink.append(evidence_factory())
    assert sink.series("unknown", Measurement.HEALTH) == []


def test_seeded_constructor_holds_initial_records(
    evidence_factory: Callable[..., Evidence],
) -> None:
    seed = [evidence_factory(value=0.01), evidence_factory(value=0.02)]
    sink = InMemoryMetricsSink(seed)
    assert sink.scan() == seed


def test_in_memory_sink_satisfies_the_protocol() -> None:
    assert isinstance(InMemoryMetricsSink(), MetricsSink)


def test_metrics_sink_is_not_the_event_log_storage() -> None:
    # The two seams are distinct: the metrics sink does not implement the event-log contract, so it
    # cannot be wired in where the event log is expected (and vice versa).
    assert not isinstance(InMemoryMetricsSink(), StorageStrategy)
