"""Signal derivation: the latest measurement wins, and health/efficacy stay separate series."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sailguarding.measurement import (
    Evidence,
    InMemoryMetricsSink,
    latest_signal,
    signal_series,
)
from sailguarding.safeguards import Measurement
from sailguarding.scoring import SafeguardSignal


def _at(minute: int) -> datetime:
    return datetime(2026, 7, 5, 12, minute, tzinfo=UTC)


def test_latest_signal_takes_the_newest_measurement(
    evidence_factory: Callable[..., Evidence],
) -> None:
    sink = InMemoryMetricsSink()
    sink.append_many(
        [
            evidence_factory(value=0.03, timestamp=_at(1)),
            evidence_factory(value=0.01, timestamp=_at(3)),  # newest
            evidence_factory(value=0.02, timestamp=_at(2)),
        ]
    )
    signal = latest_signal(sink, "no-flaky-tests", Measurement.HEALTH)
    assert signal == SafeguardSignal("no-flaky-tests", "flakiness", 0.01)


def test_latest_signal_is_none_without_evidence() -> None:
    assert latest_signal(InMemoryMetricsSink(), "no-flaky-tests", Measurement.HEALTH) is None


def test_latest_signal_is_kind_scoped(evidence_factory: Callable[..., Evidence]) -> None:
    # Health and efficacy each have their own latest; deriving one never reads the other's history.
    sink = InMemoryMetricsSink()
    sink.append_many(
        [
            evidence_factory(measures=Measurement.HEALTH, value=0.01, timestamp=_at(1)),
            evidence_factory(
                measures=Measurement.EFFICACY, metric="catch_rate", value=0.9, timestamp=_at(2)
            ),
        ]
    )
    assert latest_signal(sink, "no-flaky-tests", Measurement.HEALTH) == SafeguardSignal(
        "no-flaky-tests", "flakiness", 0.01
    )
    assert latest_signal(sink, "no-flaky-tests", Measurement.EFFICACY) == SafeguardSignal(
        "no-flaky-tests", "catch_rate", 0.9
    )


def test_signal_series_projects_values_oldest_first(
    evidence_factory: Callable[..., Evidence],
) -> None:
    sink = InMemoryMetricsSink()
    sink.append_many(
        [
            evidence_factory(value=0.03, timestamp=_at(3)),
            evidence_factory(value=0.01, timestamp=_at(1)),
            evidence_factory(value=0.02, timestamp=_at(2)),
        ]
    )
    assert signal_series(sink, "no-flaky-tests", Measurement.HEALTH) == [0.01, 0.02, 0.03]


def test_signal_series_is_kind_scoped(evidence_factory: Callable[..., Evidence]) -> None:
    sink = InMemoryMetricsSink()
    sink.append_many(
        [
            evidence_factory(measures=Measurement.HEALTH, value=0.01, timestamp=_at(1)),
            evidence_factory(measures=Measurement.EFFICACY, value=0.9, timestamp=_at(2)),
        ]
    )
    assert signal_series(sink, "no-flaky-tests", Measurement.HEALTH) == [0.01]
    assert signal_series(sink, "no-flaky-tests", Measurement.EFFICACY) == [0.9]
