"""The :class:`ActivityModelStore` implementations: in-memory and atomic file persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from sailguarding.model import (
    ActivityModel,
    ActivityModelStore,
    FileActivityModelStore,
    FileWorkspaceStore,
    InMemoryActivityModelStore,
    InMemoryWorkspaceStore,
    Workspace,
    WorkspaceStore,
)
from sailguarding.safeguards import Measurement, SafeguardKind
from sailguarding.web import scenario


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


# -- WorkspaceStore ---------------------------------------------------------------------------


def _workspace() -> Workspace:
    """A real, multi-model workspace, built through the scenario's own transforms."""
    return scenario.seed_workspace()


@pytest.fixture(params=["memory", "file"])
def workspace_store(request: pytest.FixtureRequest, tmp_path: Path) -> WorkspaceStore:
    """Both workspace store implementations, exercised through the shared Protocol contract."""
    if request.param == "memory":
        return InMemoryWorkspaceStore()
    return FileWorkspaceStore(tmp_path / "workspace.json")


def test_workspace_load_before_save_is_none(workspace_store: WorkspaceStore) -> None:
    assert workspace_store.load() is None


def test_workspace_save_then_load_round_trips_equal(workspace_store: WorkspaceStore) -> None:
    workspace = _workspace()
    workspace_store.save(workspace)
    assert workspace_store.load() == workspace


def test_workspace_save_replaces_the_previous(workspace_store: WorkspaceStore) -> None:
    workspace_store.save(Workspace.empty())
    workspace = _workspace()
    workspace_store.save(workspace)
    assert workspace_store.load() == workspace


def test_both_workspace_stores_satisfy_the_protocol() -> None:
    assert isinstance(InMemoryWorkspaceStore(), WorkspaceStore)
    assert isinstance(FileWorkspaceStore("unused.json"), WorkspaceStore)


def test_file_workspace_store_writes_canonical_json(tmp_path: Path) -> None:
    path = tmp_path / "workspace.json"
    workspace = _workspace()
    FileWorkspaceStore(path).save(workspace)
    assert path.read_text(encoding="utf-8") == workspace.to_json()


def test_file_workspace_store_load_returns_none_when_file_absent(tmp_path: Path) -> None:
    assert FileWorkspaceStore(tmp_path / "workspace.json").load() is None
