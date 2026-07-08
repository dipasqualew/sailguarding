"""The :class:`Safeguard` type: its declarations, the cadence, versioning, round-trip stability."""

from __future__ import annotations

from datetime import timedelta

import pytest

from sailguarding.safeguards import Measurement, Safeguard, SafeguardKind


def _safeguard(**over: object) -> Safeguard:
    base: dict[str, object] = {
        "id": "no-flaky-tests",
        "label": "No flaky tests",
        "metric": "flakiness",
        "kind": SafeguardKind.STRUCTURAL,
        "measures": Measurement.HEALTH,
    }
    base.update(over)
    return Safeguard(**base)  # type: ignore[arg-type]


def test_carries_its_two_declarations() -> None:
    sg = _safeguard(kind=SafeguardKind.HUMAN_DEPENDENT, measures=Measurement.EFFICACY)
    assert sg.kind is SafeguardKind.HUMAN_DEPENDENT
    assert sg.measures is Measurement.EFFICACY


def test_round_trips_through_json() -> None:
    sg = _safeguard()
    assert Safeguard.from_json(sg.to_json()) == sg


def test_round_trips_through_dict() -> None:
    sg = _safeguard(kind=SafeguardKind.HUMAN_DEPENDENT, measures=Measurement.EFFICACY)
    assert Safeguard.from_dict(sg.to_dict()) == sg


def test_enums_serialise_by_stable_string_value() -> None:
    data = _safeguard().to_dict()
    assert data["kind"] == "structural"
    assert data["measures"] == "health"


def test_serialised_form_is_versioned() -> None:
    assert _safeguard().to_dict()["schema_version"] == 2


def test_cadence_defaults_to_none_never_expires() -> None:
    sg = _safeguard()
    assert sg.cadence is None
    assert sg.to_dict()["cadence_seconds"] is None
    assert Safeguard.from_json(sg.to_json()) == sg


def test_cadence_round_trips_through_json() -> None:
    weekly = _safeguard(cadence=timedelta(days=7))
    assert weekly.cadence == timedelta(days=7)
    assert weekly.to_dict()["cadence_seconds"] == 7 * 86400
    assert Safeguard.from_json(weekly.to_json()) == weekly


def test_cadence_round_trips_a_sub_day_interval() -> None:
    # Cadence is domain-agnostic and not day-quantised — a 90-minute window round-trips too.
    hourly = _safeguard(cadence=timedelta(minutes=90))
    assert Safeguard.from_dict(hourly.to_dict()) == hourly


def test_rejects_unknown_schema_version() -> None:
    data = _safeguard().to_dict()
    data["schema_version"] = 999
    with pytest.raises(ValueError, match="unsupported Safeguard schema_version"):
        Safeguard.from_dict(data)


def test_is_domain_agnostic() -> None:
    # The same shape governs a purchase as readily as a code edit.
    sofa = _safeguard(
        id="within-budget",
        label="Within household budget",
        metric="overspend",
        kind=SafeguardKind.STRUCTURAL,
        measures=Measurement.EFFICACY,
    )
    assert Safeguard.from_json(sofa.to_json()) == sofa
