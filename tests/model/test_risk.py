"""The :class:`Risk` type: versioning and round-trip stability."""

from __future__ import annotations

import pytest

from sailguarding.model import RISK_SCHEMA_VERSION, Risk


def _risk(**over: object) -> Risk:
    base: dict[str, object] = {"id": "data-loss", "label": "Data loss"}
    base.update(over)
    return Risk(**base)  # type: ignore[arg-type]


def test_round_trips_through_json() -> None:
    risk = _risk(description="irreversibly destroying records")
    assert Risk.from_json(risk.to_json()) == risk


def test_round_trips_through_dict() -> None:
    risk = _risk()
    assert Risk.from_dict(risk.to_dict()) == risk


def test_description_defaults_to_empty() -> None:
    assert _risk().description == ""


def test_serialised_form_is_versioned() -> None:
    assert _risk().to_dict()["schema_version"] == RISK_SCHEMA_VERSION


def test_json_is_canonical_single_line() -> None:
    text = _risk().to_json()
    assert "\n" not in text
    assert ", " not in text  # tight separators


def test_rejects_unknown_schema_version() -> None:
    data = _risk().to_dict()
    data["schema_version"] = 999
    with pytest.raises(ValueError, match="unsupported Risk schema_version"):
        Risk.from_dict(data)


def test_is_domain_agnostic() -> None:
    # The same shape names a hazard of a purchase as readily as of a code edit.
    overspend = Risk(id="overspend", label="Overspend the budget", description="cost overrun")
    assert Risk.from_json(overspend.to_json()) == overspend
