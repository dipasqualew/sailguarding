"""The :class:`ActivityModelStore` implementations: in-memory and atomic file persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from sailguarding.model import (
    ActivityModel,
    ActivityModelStore,
    FileActivityModelStore,
    InMemoryActivityModelStore,
)
from sailguarding.safeguards import Measurement, SafeguardKind


def _model() -> ActivityModel:
    model, ship_id = ActivityModel.empty().add_activity(None, "Ship the update")
    model, risk_id = model.add_risk("Data loss")
    model, sg_id = model.add_safeguard(
        "Peer review", SafeguardKind.HUMAN_DEPENDENT, Measurement.EFFICACY
    )
    return model.attach_risk(ship_id, risk_id).add_mitigation(ship_id, risk_id, sg_id)


@pytest.fixture(params=["memory", "file"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> ActivityModelStore:
    """Both store implementations, exercised through the shared Protocol contract."""
    if request.param == "memory":
        return InMemoryActivityModelStore()
    return FileActivityModelStore(tmp_path / "model.json")


def test_load_before_save_is_none(store: ActivityModelStore) -> None:
    assert store.load() is None


def test_save_then_load_round_trips_equal(store: ActivityModelStore) -> None:
    model = _model()
    store.save(model)
    assert store.load() == model


def test_save_replaces_the_previous_model(store: ActivityModelStore) -> None:
    store.save(ActivityModel.empty())
    model = _model()
    store.save(model)
    assert store.load() == model


def test_both_stores_satisfy_the_protocol() -> None:
    assert isinstance(InMemoryActivityModelStore(), ActivityModelStore)
    assert isinstance(FileActivityModelStore("unused.json"), ActivityModelStore)


def test_file_store_writes_canonical_json(tmp_path: Path) -> None:
    path = tmp_path / "model.json"
    model = _model()
    FileActivityModelStore(path).save(model)
    assert path.read_text(encoding="utf-8") == model.to_json()
