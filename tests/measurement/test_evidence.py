"""The :class:`Evidence` record: kind, attestation, freshness, versioning, round-trip stability."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone

import pytest

from sailguarding.domain import Context
from sailguarding.measurement import Evidence
from sailguarding.safeguards import Measurement


def test_carries_its_kind(evidence_factory: Callable[..., Evidence]) -> None:
    health = evidence_factory(measures=Measurement.HEALTH)
    efficacy = evidence_factory(measures=Measurement.EFFICACY)
    assert health.measures is Measurement.HEALTH
    assert efficacy.measures is Measurement.EFFICACY


def test_round_trips_through_json(evidence_factory: Callable[..., Evidence]) -> None:
    e = evidence_factory(measures=Measurement.EFFICACY, metric="catch_rate", value=0.82)
    assert Evidence.from_json(e.to_json()) == e


def test_round_trips_through_dict(evidence_factory: Callable[..., Evidence]) -> None:
    e = evidence_factory()
    assert Evidence.from_dict(e.to_dict()) == e


def test_kind_serialises_by_stable_string_value(
    evidence_factory: Callable[..., Evidence],
) -> None:
    assert evidence_factory(measures=Measurement.HEALTH).to_dict()["measures"] == "health"
    assert evidence_factory(measures=Measurement.EFFICACY).to_dict()["measures"] == "efficacy"


def test_serialised_form_is_versioned(evidence_factory: Callable[..., Evidence]) -> None:
    assert evidence_factory().to_dict()["schema_version"] == 2


# --- Attestation: reasoning, the validity window, and a value-less structural claim (task 09) ---


def test_carries_reasoning_and_round_trips(evidence_factory: Callable[..., Evidence]) -> None:
    e = evidence_factory(reasoning="CI ran the suite green over the last 200 runs.")
    assert e.reasoning == "CI ran the suite green over the last 200 runs."
    assert Evidence.from_json(e.to_json()) == e


def test_validity_window_round_trips(evidence_factory: Callable[..., Evidence]) -> None:
    e = evidence_factory(valid_for=timedelta(days=7))
    assert e.valid_for == timedelta(days=7)
    assert e.to_dict()["valid_for_seconds"] == 7 * 86400
    assert Evidence.from_json(e.to_json()) == e


def test_no_window_means_never_expires(evidence_factory: Callable[..., Evidence]) -> None:
    e = evidence_factory(valid_for=None)
    assert e.expires_at is None
    assert e.to_dict()["valid_for_seconds"] is None
    assert e.is_fresh(datetime(2999, 1, 1, tzinfo=UTC))


def test_expires_at_is_derived_from_timestamp_plus_window() -> None:
    e = Evidence(
        safeguard_id="no-flaky-tests",
        metric="flakiness",
        value=0.01,
        measures=Measurement.HEALTH,
        valid_for=timedelta(days=7),
        timestamp=datetime(2026, 7, 5, 9, 0, tzinfo=UTC),
    )
    assert e.expires_at == datetime(2026, 7, 12, 9, 0, tzinfo=UTC)


def test_is_fresh_is_a_cliff_at_expiry() -> None:
    e = Evidence(
        safeguard_id="no-flaky-tests",
        metric="flakiness",
        value=0.01,
        measures=Measurement.HEALTH,
        valid_for=timedelta(days=7),
        timestamp=datetime(2026, 7, 5, 9, 0, tzinfo=UTC),
    )
    assert e.is_fresh(datetime(2026, 7, 12, 8, 59, tzinfo=UTC)) is True
    assert e.is_fresh(datetime(2026, 7, 12, 9, 0, tzinfo=UTC)) is False  # stale from the instant on


def test_structural_attestation_has_no_numeric_value() -> None:
    # A value-less structural claim ("ephemeral envs verified") is representable and round-trips.
    structural = Evidence(
        safeguard_id="ephemeral-envs",
        metric="verified",
        value=None,
        measures=Measurement.EFFICACY,
        reasoning="Every deploy provisions a throwaway env and tears it down.",
        valid_for=timedelta(days=1),
        timestamp=datetime(2026, 7, 5, 9, 0, tzinfo=UTC),
    )
    assert structural.value is None
    assert structural.to_dict()["value"] is None
    assert Evidence.from_json(structural.to_json()) == structural


def test_rejects_a_non_positive_window() -> None:
    with pytest.raises(ValueError, match="valid_for must be a positive window"):
        Evidence(
            safeguard_id="no-flaky-tests",
            metric="flakiness",
            value=0.01,
            measures=Measurement.HEALTH,
            valid_for=timedelta(0),
            timestamp=datetime(2026, 7, 5, 9, 0, tzinfo=UTC),
        )


def test_rejects_unknown_schema_version(evidence_factory: Callable[..., Evidence]) -> None:
    data = evidence_factory().to_dict()
    data["schema_version"] = 999
    with pytest.raises(ValueError, match="unsupported Evidence schema_version"):
        Evidence.from_dict(data)


def test_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="must be timezone-aware"):
        Evidence(
            safeguard_id="no-flaky-tests",
            metric="flakiness",
            value=0.01,
            measures=Measurement.HEALTH,
            timestamp=datetime(2026, 7, 5, 12, 0),  # naive
        )


def test_timestamp_normalised_to_utc() -> None:
    # 14:00 at +02:00 is 12:00 UTC; the record stores the UTC instant.
    local = datetime(2026, 7, 5, 14, 0, tzinfo=timezone(timedelta(hours=2)))
    e = Evidence(
        safeguard_id="no-flaky-tests",
        metric="flakiness",
        value=0.01,
        measures=Measurement.HEALTH,
        timestamp=local,
    )
    assert e.timestamp == datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


def test_is_domain_agnostic() -> None:
    # "return rate" for a purchase is the same shape as "revert rate" for a code change.
    ret = Evidence(
        safeguard_id="within-budget",
        metric="return_rate",
        value=0.05,
        measures=Measurement.EFFICACY,
        context=Context(home="flat-2", room="living"),
        timestamp=datetime(2026, 7, 5, 12, 0, tzinfo=UTC),
    )
    assert Evidence.from_json(ret.to_json()) == ret
