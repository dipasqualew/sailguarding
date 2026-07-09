"""The :class:`Workspace` aggregate: model navigation, cross-model import, serialisation.

Every test builds fresh models in-memory; nothing touches the filesystem.
"""

from __future__ import annotations

import pytest

from sailguarding.model import (
    WORKSPACE_SCHEMA_VERSION,
    ActivityModel,
    ContextScope,
    Workspace,
)
from sailguarding.safeguards import Measurement, SafeguardKind


def _model(model_id: str, name: str) -> ActivityModel:
    """A tiny governed model: one activity facing one risk, mitigated by one safeguard."""
    model = ActivityModel.empty(model_id=model_id, name=name)
    model, ship = model.add_activity(None, "Ship the update")
    model, risk = model.add_risk("Data loss")
    model, sg = model.add_safeguard(
        "Peer review", SafeguardKind.HUMAN_DEPENDENT, Measurement.EFFICACY
    )
    model = model.attach_risk(ship, risk).add_mitigation(ship, risk, sg)
    return model


# -- construction & queries -------------------------------------------------------------------


def test_empty_has_no_models_and_nothing_active() -> None:
    ws = Workspace.empty()
    assert ws.models == ()
    assert ws.active_id is None
    assert ws.active() is None


def test_of_makes_the_first_model_active() -> None:
    first = _model("first", "First")
    second = _model("second", "Second")
    ws = Workspace.of(first, second)
    assert ws.model_ids() == ("first", "second")
    assert ws.active_id == "first"
    assert ws.active() == first


def test_of_with_no_models_is_empty() -> None:
    assert Workspace.of() == Workspace.empty()


def test_find_returns_the_model_or_none() -> None:
    first = _model("first", "First")
    ws = Workspace.of(first)
    assert ws.find("first") == first
    assert ws.find("nope") is None


# -- model transforms -------------------------------------------------------------------------


def test_add_model_appends_and_activates_a_fresh_empty_model() -> None:
    ws, new_id = Workspace.of(_model("first", "First")).add_model("Sales")
    assert new_id == "sales"
    assert ws.model_ids() == ("first", "sales")
    assert ws.active_id == "sales"
    added = ws.find("sales")
    assert added is not None
    assert added.name == "Sales"
    assert added.top_level() == ()  # freshly empty


def test_add_model_mints_a_unique_id_on_name_collision() -> None:
    ws, _ = Workspace.empty().add_model("Sales")
    ws, second_id = ws.add_model("Sales")
    assert second_id == "sales-2"
    assert ws.model_ids() == ("sales", "sales-2")


def test_rename_model_sets_the_name() -> None:
    ws = Workspace.of(_model("first", "First"))
    renamed = ws.rename_model("first", "Renamed")
    model = renamed.find("first")
    assert model is not None and model.name == "Renamed"


def test_rename_unknown_model_raises_keyerror() -> None:
    with pytest.raises(KeyError, match="nope"):
        Workspace.empty().rename_model("nope", "x")


def test_remove_model_active_falls_back_to_first_remaining() -> None:
    ws = Workspace.of(_model("first", "First"), _model("second", "Second"))
    removed = ws.remove_model("first")  # active was "first"
    assert removed.model_ids() == ("second",)
    assert removed.active_id == "second"


def test_remove_the_last_model_leaves_nothing_active() -> None:
    ws = Workspace.of(_model("only", "Only"))
    removed = ws.remove_model("only")
    assert removed.models == ()
    assert removed.active_id is None


def test_remove_a_non_active_model_keeps_the_active_one() -> None:
    ws = Workspace.of(_model("first", "First"), _model("second", "Second"))
    removed = ws.remove_model("second")  # active is "first", untouched
    assert removed.active_id == "first"


def test_remove_unknown_model_raises_keyerror() -> None:
    with pytest.raises(KeyError, match="nope"):
        Workspace.of(_model("first", "First")).remove_model("nope")


def test_select_switches_the_active_model() -> None:
    ws = Workspace.of(_model("first", "First"), _model("second", "Second"))
    assert ws.select("second").active_id == "second"


def test_select_unknown_model_raises_keyerror() -> None:
    with pytest.raises(KeyError, match="nope"):
        Workspace.of(_model("first", "First")).select("nope")


def test_replace_model_swaps_by_id() -> None:
    ws = Workspace.of(_model("first", "First"), _model("second", "Second"))
    replacement = ws.find("first").set_name("Replaced")  # type: ignore[union-attr]
    replaced = ws.replace_model(replacement)
    model = replaced.find("first")
    assert model is not None and model.name == "Replaced"
    assert replaced.model_ids() == ("first", "second")  # order preserved


def test_replace_unknown_model_id_raises_keyerror() -> None:
    stranger = _model("stranger", "Stranger")
    with pytest.raises(KeyError, match="stranger"):
        Workspace.of(_model("first", "First")).replace_model(stranger)


# -- cross-model import -----------------------------------------------------------------------


def test_import_activity_brings_the_subtree_and_its_governance() -> None:
    source = _model("source", "Source")
    target = ActivityModel.empty(model_id="target", name="Target")
    ws = Workspace.of(target, source)
    ship = source.top_level()[0].id

    imported, new_id = ws.import_into("target", "source", "activity", ship)

    grown = imported.find("target")
    assert grown is not None
    # The subtree landed under a fresh id, governed (its risk came along).
    assert grown.tree.find(new_id) is not None
    assert grown.risks_for(new_id) != ()
    # The source model is untouched.
    assert imported.find("source") == source


def test_import_risk_dedupes_by_id() -> None:
    source = _model("source", "Source")
    target = _model("target", "Target")  # already has a "data-loss" risk
    ws = Workspace.of(target, source)
    risk_id = source.risks[0].id

    imported, new_id = ws.import_into("target", "source", "risk", risk_id)

    grown = imported.find("target")
    assert grown is not None
    assert new_id == risk_id
    assert [r.id for r in grown.risks] == [risk_id]  # not duplicated


def test_import_safeguard_dedupes_by_id() -> None:
    source = _model("source", "Source")
    target = _model("target", "Target")  # already has a "peer-review" safeguard
    ws = Workspace.of(target, source)
    sg_id = source.safeguards[0].id

    imported, new_id = ws.import_into("target", "source", "safeguard", sg_id)

    grown = imported.find("target")
    assert grown is not None
    assert new_id == sg_id
    assert [s.id for s in grown.safeguards] == [sg_id]  # not duplicated


def test_import_leaves_the_source_untouched() -> None:
    source = _model("source", "Source")
    target = ActivityModel.empty(model_id="target", name="Target")
    ws = Workspace.of(target, source)

    imported, _ = ws.import_into("target", "source", "safeguard", source.safeguards[0].id)

    assert imported.find("source") == source


def test_import_unknown_target_model_raises_keyerror() -> None:
    ws = Workspace.of(_model("source", "Source"))
    with pytest.raises(KeyError, match="nope"):
        ws.import_into("nope", "source", "risk", "data-loss")


def test_import_unknown_source_model_raises_keyerror() -> None:
    ws = Workspace.of(_model("target", "Target"))
    with pytest.raises(KeyError, match="nope"):
        ws.import_into("target", "nope", "risk", "data-loss")


def test_import_unknown_entity_raises_keyerror() -> None:
    ws = Workspace.of(_model("target", "Target"), _model("source", "Source"))
    with pytest.raises(KeyError, match="risk"):
        ws.import_into("target", "source", "risk", "does-not-exist")


def test_import_unknown_kind_raises_valueerror() -> None:
    ws = Workspace.of(_model("target", "Target"), _model("source", "Source"))
    with pytest.raises(ValueError, match="unknown import kind"):
        ws.import_into("target", "source", "bogus", "data-loss")  # type: ignore[arg-type]


# -- serialisation ----------------------------------------------------------------------------


def _rich_workspace() -> Workspace:
    product = _model("product", "Product").set_applies_when(
        ContextScope.empty().set_dimension("repo", ("checkout", "billing"))
    )
    sales = _model("sales", "Sales").set_applies_when(
        ContextScope.empty().set_dimension("team", ("sales",))
    )
    return Workspace.of(product, sales).select("sales")


def test_round_trips_through_json() -> None:
    ws = _rich_workspace()
    assert Workspace.from_json(ws.to_json()) == ws


def test_round_trips_through_dict() -> None:
    ws = _rich_workspace()
    assert Workspace.from_dict(ws.to_dict()) == ws


def test_json_preserves_the_active_id() -> None:
    ws = _rich_workspace()
    assert Workspace.from_json(ws.to_json()).active_id == "sales"


def test_json_is_canonical_single_line() -> None:
    assert "\n" not in _rich_workspace().to_json()


def test_serialised_form_is_versioned() -> None:
    assert Workspace.empty().to_dict()["schema_version"] == WORKSPACE_SCHEMA_VERSION


def test_rejects_unknown_schema_version() -> None:
    data = _rich_workspace().to_dict()
    data["schema_version"] = 999
    with pytest.raises(ValueError, match="unsupported Workspace schema_version"):
        Workspace.from_dict(data)
