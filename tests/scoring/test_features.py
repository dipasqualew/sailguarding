"""Feature-vector schema: versioned, serialisable, round-trip stable.

Covers the acceptance criterion that the feature vector round-trips losslessly and refuses an
unknown schema version — the property the decision log leans on to reproduce inputs exactly.
"""

from __future__ import annotations

import pytest

from sailguarding.domain import Context
from sailguarding.scoring import (
    FEATURE_SCHEMA_VERSION,
    FeatureVector,
    SafeguardSignal,
    feature_vector,
)


def _rich_vector() -> FeatureVector:
    return FeatureVector(
        signals=(
            SafeguardSignal(safeguard_id="impact", metric="blast_radius", value=3.0),
            SafeguardSignal(safeguard_id="no-flaky-tests", metric="flakiness", value=0.004),
        ),
        context=Context(repo="checkout", team="core", is_production=True),
        remaining_budget=0.42,
        action_id="write-tests",
    )


def test_round_trips_through_json() -> None:
    vector = _rich_vector()
    assert FeatureVector.from_json(vector.to_json()) == vector


def test_round_trips_through_dict() -> None:
    vector = _rich_vector()
    assert FeatureVector.from_dict(vector.to_dict()) == vector


def test_json_is_canonical_and_byte_stable() -> None:
    vector = _rich_vector()
    # Same record, same bytes — a git-diffable, append-only log line.
    assert vector.to_json() == vector.to_json()
    assert '"schema_version":1' in vector.to_json()


def test_defaults_are_a_full_budget_empty_vector() -> None:
    empty = FeatureVector()
    assert empty.signals == ()
    assert empty.remaining_budget == 1.0
    assert empty.action_id is None
    assert empty.schema_version == FEATURE_SCHEMA_VERSION
    assert FeatureVector.from_json(empty.to_json()) == empty


def test_signal_lookup_by_safeguard_id() -> None:
    vector = _rich_vector()
    assert vector.signal("no-flaky-tests").metric == "flakiness"  # type: ignore[union-attr]
    assert vector.signal("absent") is None


def test_unknown_schema_version_is_rejected() -> None:
    data = _rich_vector().to_dict()
    data["schema_version"] = 999
    with pytest.raises(ValueError, match="unsupported FeatureVector schema_version"):
        FeatureVector.from_dict(data)


def test_feature_vector_helper_coerces_context_from_mapping() -> None:
    vector = feature_vector(
        [SafeguardSignal("impact", "blast_radius", 1.0)],
        context={"repo": "checkout"},
        remaining_budget=0.5,
    )
    assert isinstance(vector.context, Context)
    assert vector.context["repo"] == "checkout"
