"""The :class:`Evidence` record: kind, versioning, UTC normalisation, round-trip stability."""

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
    assert evidence_factory().to_dict()["schema_version"] == 1


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
