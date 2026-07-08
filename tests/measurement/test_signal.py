"""Signal derivation: latest-fresh wins, health/efficacy stay separate, stale contributes nothing.

Every derivation is against an **injected** ``now`` — never wall time — so crossing an attestation's
expiry window is deterministic. The load-bearing property (task 09) is the freshness cliff: evidence
past its window is stale and yields no signal, so a safeguard with only stale evidence is
indistinguishable from one with no evidence at all — it fails toward caution.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from sailguarding.measurement import (
    Evidence,
    InMemoryMetricsSink,
    latest_signal,
    signal_series,
)
from sailguarding.safeguards import Measurement
from sailguarding.scoring import SafeguardSignal

WEEK = timedelta(days=7)


def _at(day: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, day, 12, minute, tzinfo=UTC)


# --- The reduction: latest measurement wins, health and efficacy never mix ---------------------


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
    signal = latest_signal(sink, "no-flaky-tests", Measurement.HEALTH, now=_at(3))
    assert signal == SafeguardSignal("no-flaky-tests", "flakiness", 0.01)


def test_latest_signal_is_none_without_evidence() -> None:
    sink = InMemoryMetricsSink()
    assert latest_signal(sink, "no-flaky-tests", Measurement.HEALTH, now=_at(3)) is None


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
    assert latest_signal(sink, "no-flaky-tests", Measurement.HEALTH, now=_at(2)) == SafeguardSignal(
        "no-flaky-tests", "flakiness", 0.01
    )
    assert latest_signal(
        sink, "no-flaky-tests", Measurement.EFFICACY, now=_at(2)
    ) == SafeguardSignal("no-flaky-tests", "catch_rate", 0.9)


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
    assert signal_series(sink, "no-flaky-tests", Measurement.HEALTH, now=_at(3)) == [
        0.01,
        0.02,
        0.03,
    ]


def test_signal_series_is_kind_scoped(evidence_factory: Callable[..., Evidence]) -> None:
    sink = InMemoryMetricsSink()
    sink.append_many(
        [
            evidence_factory(measures=Measurement.HEALTH, value=0.01, timestamp=_at(1)),
            evidence_factory(measures=Measurement.EFFICACY, value=0.9, timestamp=_at(2)),
        ]
    )
    assert signal_series(sink, "no-flaky-tests", Measurement.HEALTH, now=_at(2)) == [0.01]
    assert signal_series(sink, "no-flaky-tests", Measurement.EFFICACY, now=_at(2)) == [0.9]


# --- The freshness cliff (task 09): stale evidence contributes no signal ------------------------


def test_expired_evidence_yields_no_signal(evidence_factory: Callable[..., Evidence]) -> None:
    # One point, valid for a week, read a fortnight later: past its window, so no signal at all.
    sink = InMemoryMetricsSink()
    sink.append(evidence_factory(value=0.01, valid_for=WEEK, timestamp=_at(1)))
    assert latest_signal(sink, "no-flaky-tests", Measurement.HEALTH, now=_at(1)) is not None
    assert latest_signal(sink, "no-flaky-tests", Measurement.HEALTH, now=_at(15)) is None


def test_fresh_evidence_holds_up_to_the_cliff(evidence_factory: Callable[..., Evidence]) -> None:
    # A cliff, not a ramp: fresh strictly before expiry, stale from that instant on.
    sink = InMemoryMetricsSink()
    e = evidence_factory(value=0.01, valid_for=WEEK, timestamp=_at(1))
    sink.append(e)
    expires = e.expires_at
    assert expires is not None
    just_before = expires - timedelta(seconds=1)
    assert latest_signal(sink, "no-flaky-tests", Measurement.HEALTH, now=just_before) is not None
    assert latest_signal(sink, "no-flaky-tests", Measurement.HEALTH, now=expires) is None


def test_stale_newest_hides_an_older_fresh_point(
    evidence_factory: Callable[..., Evidence],
) -> None:
    # The newest point is what "current" means; if it has lapsed the safeguard is stale even though
    # an older (also-lapsed) point exists. Both expired here → nothing.
    sink = InMemoryMetricsSink()
    sink.append_many(
        [
            evidence_factory(value=0.03, valid_for=WEEK, timestamp=_at(1)),
            evidence_factory(value=0.01, valid_for=WEEK, timestamp=_at(2)),
        ]
    )
    assert latest_signal(sink, "no-flaky-tests", Measurement.HEALTH, now=_at(20)) is None


def test_only_stale_evidence_is_indistinguishable_from_none(
    evidence_factory: Callable[..., Evidence],
) -> None:
    # The subscription's whole point: a safeguard whose only evidence has lapsed derives the exact
    # same (no) signal as one that never had any — so both fail toward caution downstream.
    empty = InMemoryMetricsSink()
    stale = InMemoryMetricsSink([evidence_factory(value=0.01, valid_for=WEEK, timestamp=_at(1))])
    now = _at(30)
    assert latest_signal(empty, "no-flaky-tests", Measurement.HEALTH, now=now) is None
    assert latest_signal(stale, "no-flaky-tests", Measurement.HEALTH, now=now) is None


def test_renewing_with_a_fresh_point_restores_the_signal(
    evidence_factory: Callable[..., Evidence],
) -> None:
    sink = InMemoryMetricsSink([evidence_factory(value=0.01, valid_for=WEEK, timestamp=_at(1))])
    now = _at(20)
    assert latest_signal(sink, "no-flaky-tests", Measurement.HEALTH, now=now) is None
    # Renew: post a fresh attestation stamped at now — the signal comes back.
    sink.append(evidence_factory(value=0.005, valid_for=WEEK, timestamp=now))
    assert latest_signal(sink, "no-flaky-tests", Measurement.HEALTH, now=now) == SafeguardSignal(
        "no-flaky-tests", "flakiness", 0.005
    )


def test_evidence_without_a_window_never_expires(
    evidence_factory: Callable[..., Evidence],
) -> None:
    # valid_for=None is a never-expiring attestation — fresh at any "now", however far out.
    sink = InMemoryMetricsSink([evidence_factory(value=0.01, valid_for=None, timestamp=_at(1))])
    far_future = datetime(2036, 1, 1, tzinfo=UTC)
    assert latest_signal(
        sink, "no-flaky-tests", Measurement.HEALTH, now=far_future
    ) == SafeguardSignal("no-flaky-tests", "flakiness", 0.01)


def test_signal_series_drops_stale_points(evidence_factory: Callable[..., Evidence]) -> None:
    sink = InMemoryMetricsSink()
    sink.append_many(
        [
            evidence_factory(value=0.03, valid_for=WEEK, timestamp=_at(1)),  # stale at now
            evidence_factory(value=0.02, valid_for=WEEK, timestamp=_at(2)),  # stale at now
            evidence_factory(value=0.01, valid_for=WEEK, timestamp=_at(12)),  # fresh at now
        ]
    )
    # now sits after the first two windows (day 8, day 9) but inside the third's (day 19).
    assert signal_series(sink, "no-flaky-tests", Measurement.HEALTH, now=_at(13)) == [0.01]


# --- Structural attestations (value is None) carry no numeric signal ----------------------------


def test_structural_attestation_yields_no_numeric_signal(
    evidence_factory: Callable[..., Evidence],
) -> None:
    # A value-less structural claim is representable, but it is not a *number* — so numeric signal
    # derivation skips it. Turning it into autonomy is capability modelling (task 11), not here.
    sink = InMemoryMetricsSink([evidence_factory(value=None, valid_for=WEEK, timestamp=_at(1))])
    assert latest_signal(sink, "no-flaky-tests", Measurement.HEALTH, now=_at(1)) is None
    assert signal_series(sink, "no-flaky-tests", Measurement.HEALTH, now=_at(1)) == []


@pytest.mark.parametrize("kind", [Measurement.HEALTH, Measurement.EFFICACY])
def test_structural_is_skipped_but_a_numeric_point_still_reads(
    evidence_factory: Callable[..., Evidence], kind: Measurement
) -> None:
    # A structural point next to a numeric one of the same kind: the numeric one is the signal.
    sink = InMemoryMetricsSink()
    sink.append_many(
        [
            evidence_factory(measures=kind, value=0.02, valid_for=WEEK, timestamp=_at(1)),
            evidence_factory(measures=kind, value=None, valid_for=WEEK, timestamp=_at(2)),
        ]
    )
    signal = latest_signal(sink, "no-flaky-tests", kind, now=_at(3))
    assert signal is not None and signal.value == 0.02
