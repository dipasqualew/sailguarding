"""The :class:`ActivityModel` aggregate: transforms, queries, and round-trip serialisation.

Every test injects a fresh model built in-memory; nothing touches the filesystem.
"""

from __future__ import annotations

import pytest

from sailguarding.model import (
    DEFAULT_MODEL_ID,
    MODEL_SCHEMA_VERSION,
    ROOT_ID,
    ActivityModel,
    ContextScope,
    Risk,
)
from sailguarding.safeguards import Measurement, Safeguard, SafeguardKind


def _add_review(model: ActivityModel) -> tuple[ActivityModel, str]:
    """Add the shared human-dependent "Peer review" safeguard used across these tests."""
    return model.add_safeguard("Peer review", SafeguardKind.HUMAN_DEPENDENT, Measurement.EFFICACY)


def test_empty_has_only_the_synthetic_root() -> None:
    model = ActivityModel.empty()
    assert model.tree.find(ROOT_ID) is not None
    assert model.top_level() == ()
    assert model.risks == ()
    assert model.safeguards == ()
    assert model.activity_risks == frozenset()
    assert model.mitigations == frozenset()


# -- tree transforms --------------------------------------------------------------------------


def test_add_activity_at_top_level_grafts_under_the_synthetic_root() -> None:
    model, ship_id = ActivityModel.empty().add_activity(None, "Ship the update")
    assert ship_id == "ship-the-update"
    assert [a.id for a in model.top_level()] == ["ship-the-update"]
    assert model.tree.find(ship_id) is not None
    assert model.tree.parent_of(ship_id).id == ROOT_ID  # type: ignore[union-attr]


def test_add_activity_supports_multiple_top_level_activities() -> None:
    model, _ = ActivityModel.empty().add_activity(None, "Ship the update")
    model, _ = model.add_activity(None, "Buy a sofa")
    assert [a.label for a in model.top_level()] == ["Ship the update", "Buy a sofa"]


def test_add_activity_nests_under_an_explicit_parent() -> None:
    model, ship_id = ActivityModel.empty().add_activity(None, "Ship the update")
    model, tests_id = model.add_activity(ship_id, "Write the tests")
    assert model.tree.parent_of(tests_id).id == ship_id  # type: ignore[union-attr]


def test_add_activity_is_pure() -> None:
    original = ActivityModel.empty()
    grown, _ = original.add_activity(None, "Ship the update")
    assert original.top_level() == ()  # receiver untouched
    assert grown.top_level() != ()


def test_add_activity_under_a_missing_parent_raises_keyerror() -> None:
    with pytest.raises(KeyError, match="nope"):
        ActivityModel.empty().add_activity("nope", "Write the tests")


def test_generated_ids_are_unique_with_a_numeric_suffix() -> None:
    model, first = ActivityModel.empty().add_activity(None, "Write the tests")
    model, second = model.add_activity(None, "Write the tests")
    assert first == "write-the-tests"
    assert second == "write-the-tests-2"


def test_slugify_collapses_non_alphanumeric_runs() -> None:
    _, new_id = ActivityModel.empty().add_activity(None, "  Ship  the!!! update  ")
    assert new_id == "ship-the-update"


def test_rename_activity_changes_the_label_only() -> None:
    model, ship_id = ActivityModel.empty().add_activity(None, "Ship the update")
    renamed = model.rename_activity(ship_id, "Ship the release")
    assert renamed.tree.find(ship_id).label == "Ship the release"  # type: ignore[union-attr]
    assert model.tree.find(ship_id).label == "Ship the update"  # type: ignore[union-attr]


def test_rename_missing_activity_raises_keyerror() -> None:
    with pytest.raises(KeyError, match="nope"):
        ActivityModel.empty().rename_activity("nope", "whatever")


def test_remove_activity_drops_the_node_and_its_subtree() -> None:
    model, ship_id = ActivityModel.empty().add_activity(None, "Ship the update")
    model, tests_id = model.add_activity(ship_id, "Write the tests")
    model, _ = model.add_activity(tests_id, "Context tests")
    pruned = model.remove_activity(ship_id)
    assert pruned.top_level() == ()
    assert pruned.tree.find(tests_id) is None


def test_remove_activity_cascades_edges_of_the_whole_subtree() -> None:
    model, ship_id = ActivityModel.empty().add_activity(None, "Ship the update")
    model, tests_id = model.add_activity(ship_id, "Write the tests")
    model, risk_id = model.add_risk("Data loss")
    model, sg_id = _add_review(model)
    # An edge on the parent AND an edge on the descendant — both must be cascaded away.
    model = model.attach_risk(ship_id, risk_id)
    model = model.attach_risk(tests_id, risk_id)
    model = model.add_mitigation(tests_id, risk_id, sg_id)

    pruned = model.remove_activity(ship_id)

    assert pruned.activity_risks == frozenset()
    assert pruned.mitigations == frozenset()


def test_remove_the_synthetic_root_is_a_noop() -> None:
    model, _ = ActivityModel.empty().add_activity(None, "Ship the update")
    assert model.remove_activity(ROOT_ID) == model


def test_remove_missing_activity_raises_keyerror() -> None:
    with pytest.raises(KeyError, match="nope"):
        ActivityModel.empty().remove_activity("nope")


# -- library transforms -----------------------------------------------------------------------


def test_add_risk_appends_to_the_library_and_returns_its_id() -> None:
    model, risk_id = ActivityModel.empty().add_risk("Data loss", "destroying records")
    assert risk_id == "data-loss"
    assert model.find_risk(risk_id) == Risk(
        id="data-loss", label="Data loss", description="destroying records"
    )


def test_add_risk_ids_are_unique() -> None:
    model, first = ActivityModel.empty().add_risk("Data loss")
    model, second = model.add_risk("Data loss")
    assert (first, second) == ("data-loss", "data-loss-2")


def test_add_safeguard_appends_to_the_library_and_returns_its_id() -> None:
    model, sg_id = ActivityModel.empty().add_safeguard(
        "Spending cap", SafeguardKind.STRUCTURAL, Measurement.EFFICACY, metric="overspend"
    )
    assert sg_id == "spending-cap"
    stored = model.find_safeguard(sg_id)
    assert stored == Safeguard(
        id="spending-cap",
        label="Spending cap",
        metric="overspend",
        kind=SafeguardKind.STRUCTURAL,
        measures=Measurement.EFFICACY,
    )


# -- edge transforms --------------------------------------------------------------------------


def test_attach_and_detach_risk() -> None:
    model, ship_id = ActivityModel.empty().add_activity(None, "Ship the update")
    model, risk_id = model.add_risk("Data loss")
    attached = model.attach_risk(ship_id, risk_id)
    assert (ship_id, risk_id) in attached.activity_risks
    detached = attached.detach_risk(ship_id, risk_id)
    assert (ship_id, risk_id) not in detached.activity_risks


def test_detach_risk_drops_its_mitigations() -> None:
    model, ship_id = ActivityModel.empty().add_activity(None, "Ship the update")
    model, risk_id = model.add_risk("Data loss")
    model, sg_id = _add_review(model)
    model = model.attach_risk(ship_id, risk_id).add_mitigation(ship_id, risk_id, sg_id)

    detached = model.detach_risk(ship_id, risk_id)

    assert detached.mitigations == frozenset()


def test_attach_risk_validates_activity_and_risk() -> None:
    model, ship_id = ActivityModel.empty().add_activity(None, "Ship the update")
    model, risk_id = model.add_risk("Data loss")
    with pytest.raises(KeyError, match="activity"):
        model.attach_risk("nope", risk_id)
    with pytest.raises(KeyError, match="risk"):
        model.attach_risk(ship_id, "nope")


def test_add_and_remove_mitigation() -> None:
    model, ship_id = ActivityModel.empty().add_activity(None, "Ship the update")
    model, risk_id = model.add_risk("Data loss")
    model, sg_id = _add_review(model)
    model = model.attach_risk(ship_id, risk_id)

    added = model.add_mitigation(ship_id, risk_id, sg_id)
    assert (ship_id, risk_id, sg_id) in added.mitigations
    removed = added.remove_mitigation(ship_id, risk_id, sg_id)
    assert (ship_id, risk_id, sg_id) not in removed.mitigations


def test_add_mitigation_validates_all_three_references() -> None:
    model, ship_id = ActivityModel.empty().add_activity(None, "Ship the update")
    model, risk_id = model.add_risk("Data loss")
    model, sg_id = _add_review(model)
    with pytest.raises(KeyError, match="activity"):
        model.add_mitigation("nope", risk_id, sg_id)
    with pytest.raises(KeyError, match="risk"):
        model.add_mitigation(ship_id, "nope", sg_id)
    with pytest.raises(KeyError, match="safeguard"):
        model.add_mitigation(ship_id, risk_id, "nope")


# -- query helpers ----------------------------------------------------------------------------


def _populated() -> tuple[ActivityModel, dict[str, str]]:
    """A model with two activities sharing one risk and one safeguard — the reuse scenario."""
    model, ship_id = ActivityModel.empty().add_activity(None, "Ship the update")
    model, buy_id = model.add_activity(None, "Buy a sofa")
    model, loss_id = model.add_risk("Data loss")
    model, cost_id = model.add_risk("Opportunity cost")
    model, review_id = model.add_safeguard(
        "Peer review", SafeguardKind.HUMAN_DEPENDENT, Measurement.EFFICACY
    )
    # Data loss is faced by BOTH activities, and peer review mitigates it on BOTH — the shared case.
    model = model.attach_risk(ship_id, loss_id).add_mitigation(ship_id, loss_id, review_id)
    model = model.attach_risk(buy_id, loss_id).add_mitigation(buy_id, loss_id, review_id)
    # Opportunity cost is faced only by the purchase.
    model = model.attach_risk(buy_id, cost_id)
    ids = {"ship": ship_id, "buy": buy_id, "loss": loss_id, "cost": cost_id, "review": review_id}
    return model, ids


def test_risks_for_returns_the_activitys_risks() -> None:
    model, ids = _populated()
    assert [r.id for r in model.risks_for(ids["ship"])] == [ids["loss"]]
    assert [r.id for r in model.risks_for(ids["buy"])] == [ids["loss"], ids["cost"]]


def test_safeguards_for_returns_the_mitigating_safeguards() -> None:
    model, ids = _populated()
    assert [s.id for s in model.safeguards_for(ids["ship"], ids["loss"])] == [ids["review"]]
    assert model.safeguards_for(ids["buy"], ids["cost"]) == ()


def test_activities_using_risk_counts_distinct_activities() -> None:
    model, ids = _populated()
    assert model.activities_using_risk(ids["loss"]) == tuple(sorted([ids["ship"], ids["buy"]]))
    assert model.activities_using_risk(ids["cost"]) == (ids["buy"],)


def test_activities_using_safeguard_counts_two_distinct_activities_for_a_shared_safeguard() -> None:
    model, ids = _populated()
    using = model.activities_using_safeguard(ids["review"])
    assert using == tuple(sorted([ids["ship"], ids["buy"]]))
    assert len(using) == 2  # the key reuse count


def test_find_risk_and_find_safeguard_miss_return_none() -> None:
    model, _ = _populated()
    assert model.find_risk("nope") is None
    assert model.find_safeguard("nope") is None


# -- serialisation ----------------------------------------------------------------------------


def test_round_trips_through_json_with_a_full_model() -> None:
    model, _ = _populated()
    # Add a nested activity so the tree is non-trivial too.
    model, _ = model.add_activity(model.top_level()[0].id, "Write the tests")
    assert ActivityModel.from_json(model.to_json()) == model


def test_round_trips_through_dict() -> None:
    model, _ = _populated()
    assert ActivityModel.from_dict(model.to_dict()) == model


def test_json_is_canonical_single_line() -> None:
    model, _ = _populated()
    text = model.to_json()
    assert "\n" not in text


def test_serialised_form_is_versioned() -> None:
    assert ActivityModel.empty().to_dict()["schema_version"] == MODEL_SCHEMA_VERSION


def test_rejects_unknown_schema_version() -> None:
    data = ActivityModel.empty().to_dict()
    data["schema_version"] = 999
    with pytest.raises(ValueError, match="unsupported ActivityModel schema_version"):
        ActivityModel.from_dict(data)


# -- identity & applicability -----------------------------------------------------------------


def test_empty_defaults_to_the_default_model_id_and_no_name() -> None:
    model = ActivityModel.empty()
    assert model.id == DEFAULT_MODEL_ID == "model"
    assert model.name == ""
    assert model.applies_when == ContextScope.empty()


def test_empty_sets_the_given_id_and_name() -> None:
    model = ActivityModel.empty(model_id="sales", name="Sales")
    assert model.id == "sales"
    assert model.name == "Sales"


def test_set_name_returns_a_new_model_with_the_name() -> None:
    model = ActivityModel.empty(model_id="sales")
    named = model.set_name("Sales")
    assert named.name == "Sales"
    assert named.id == "sales"  # id unchanged
    assert model.name == ""  # receiver untouched


def test_set_applies_when_replaces_the_scope() -> None:
    scope = ContextScope.empty().set_dimension("repo", ("checkout", "billing"))
    model = ActivityModel.empty().set_applies_when(scope)
    assert model.applies_when == scope


def test_round_trips_with_a_non_empty_applies_when() -> None:
    scope = ContextScope.empty().set_dimension("repo", ("checkout", "billing"))
    model, _ = _populated()
    model = model.set_name("Product").set_applies_when(scope)
    reloaded = ActivityModel.from_dict(model.to_dict())
    assert reloaded == model
    assert reloaded.applies_when == scope
    assert reloaded.name == "Product"


# -- import (copy from another model) ---------------------------------------------------------


def test_import_risk_appends_a_new_risk() -> None:
    model = ActivityModel.empty()
    risk = Risk(id="data-loss", label="Data loss", description="destroying records")
    imported, risk_id = model.import_risk(risk)
    assert risk_id == "data-loss"
    assert imported.find_risk("data-loss") == risk
    assert model.risks == ()  # receiver untouched


def test_import_risk_dedupes_by_id() -> None:
    model, existing_id = ActivityModel.empty().add_risk("Data loss")
    incoming = Risk(id=existing_id, label="Different label")
    imported, risk_id = model.import_risk(incoming)
    assert risk_id == existing_id
    assert imported is model  # unchanged; the existing risk is reused
    assert model.find_risk(existing_id).label == "Data loss"  # type: ignore[union-attr]


def test_import_safeguard_appends_a_new_safeguard() -> None:
    model = ActivityModel.empty()
    safeguard = Safeguard(
        id="peer-review",
        label="Peer review",
        metric="",
        kind=SafeguardKind.HUMAN_DEPENDENT,
        measures=Measurement.EFFICACY,
    )
    imported, sg_id = model.import_safeguard(safeguard)
    assert sg_id == "peer-review"
    assert imported.find_safeguard("peer-review") == safeguard


def test_import_safeguard_dedupes_by_id() -> None:
    model, existing_id = _add_review(ActivityModel.empty())
    incoming = Safeguard(
        id=existing_id,
        label="Different label",
        metric="",
        kind=SafeguardKind.STRUCTURAL,
        measures=Measurement.HEALTH,
    )
    imported, sg_id = model.import_safeguard(incoming)
    assert sg_id == existing_id
    assert imported is model  # unchanged; the existing safeguard is reused


def _source_with_governed_subtree() -> tuple[ActivityModel, str]:
    """A source model whose "Test software" activity faces a risk mitigated by a safeguard."""
    source, _ = ActivityModel.empty().add_activity(None, "Write software")
    source, test = source.add_activity(None, "Test software")
    source, risk = source.add_risk("Break capabilities")
    source, sg = _add_review(source)
    source = source.attach_risk(test, risk).add_mitigation(test, risk, sg)
    return source, test


def test_import_activity_gives_fresh_ids_and_reslugs_on_collision() -> None:
    source, test = _source_with_governed_subtree()
    # The target already has a "test-software" activity, so the import re-slugs.
    target, _ = ActivityModel.empty().add_activity(None, "Test software")
    imported, new_id = target.import_activity(source, test)
    assert new_id == "test-software-2"
    assert imported.tree.find("test-software-2") is not None


def test_import_activity_brings_referenced_governance_and_remapped_edges() -> None:
    source, test = _source_with_governed_subtree()
    target = ActivityModel.empty()
    imported, new_id = target.import_activity(source, test)
    # The referenced risk & safeguard came along, and the edges point at the fresh activity id.
    assert imported.find_risk("break-capabilities") is not None
    assert imported.find_safeguard("peer-review") is not None
    assert imported.risks_for(new_id) != ()
    assert imported.safeguards_for(new_id, "break-capabilities") != ()


def test_import_activity_leaves_the_source_untouched() -> None:
    source, test = _source_with_governed_subtree()
    before = source.to_json()
    ActivityModel.empty().import_activity(source, test)
    assert source.to_json() == before


def test_import_activity_missing_activity_raises_keyerror() -> None:
    source = ActivityModel.empty()
    with pytest.raises(KeyError, match="nope"):
        ActivityModel.empty().import_activity(source, "nope")


def test_import_activity_missing_parent_raises_keyerror() -> None:
    source, test = _source_with_governed_subtree()
    with pytest.raises(KeyError, match="nope"):
        ActivityModel.empty().import_activity(source, test, parent_id="nope")


# -- v1 back-compat read ----------------------------------------------------------------------


def test_reads_a_v1_record_without_identity_and_re_emits_at_v2() -> None:
    model, _ = _populated()
    data = model.to_dict()
    # Strip the v2-only fields and stamp it as a legacy v1 record.
    data["schema_version"] = 1
    del data["id"]
    del data["name"]
    del data["applies_when"]

    loaded = ActivityModel.from_dict(data)

    assert loaded.id == DEFAULT_MODEL_ID
    assert loaded.name == ""
    assert loaded.applies_when == ContextScope.empty()
    # A record is always re-emitted at the current version.
    assert loaded.schema_version == MODEL_SCHEMA_VERSION == 2
    assert loaded.to_dict()["schema_version"] == 2


def test_from_dict_accepts_versions_1_and_2_but_rejects_others() -> None:
    data = ActivityModel.empty().to_dict()
    data["schema_version"] = 1
    assert ActivityModel.from_dict(data).schema_version == MODEL_SCHEMA_VERSION
    data["schema_version"] = 2
    assert ActivityModel.from_dict(data).schema_version == MODEL_SCHEMA_VERSION
    data["schema_version"] = 999
    with pytest.raises(ValueError, match="unsupported ActivityModel schema_version"):
        ActivityModel.from_dict(data)
