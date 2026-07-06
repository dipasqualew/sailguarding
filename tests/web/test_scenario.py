"""The demo scenario wires the real engine: assembly, ceiling breakdown, classification."""

from __future__ import annotations

from sailguarding.web import scenario


def test_assemble_features_carries_one_signal_per_safeguard() -> None:
    features = scenario.assemble_features(
        flakiness=0.004, services_affected=2.0, remaining_budget=0.7
    )
    assert {s.safeguard_id for s in features.signals} == {"impact", "no-flaky-tests"}
    assert features.remaining_budget == 0.7
    assert features.action_id == "write-tests"


def test_ceiling_breakdown_marks_exactly_one_binding_minimum() -> None:
    features = scenario.assemble_features(
        flakiness=0.004, services_affected=1.0, remaining_budget=0.3
    )
    rows = scenario.ceiling_breakdown(features)
    binding = [r for r in rows if r["binding"]]
    assert len(binding) == 1
    assert binding[0]["id"] == "remaining-budget"  # budget 0.3 is the smallest ceiling
    assert binding[0]["ceiling"] == min(float(r["ceiling"]) for r in rows)  # type: ignore[arg-type]


def test_scoring_function_is_the_reference_min_composition() -> None:
    fn = scenario.scoring_function()
    assert fn.name == "min-composition"
    features = scenario.assemble_features(
        flakiness=0.0, services_affected=100.0, remaining_budget=1.0
    )
    assert fn.score(features) == 0.0  # catastrophic impact caps hard


def test_registry_resolves_both_safeguards_for_the_demo_action() -> None:
    rows = scenario.safeguard_panel()
    by_id = {r["id"]: r for r in rows}
    assert set(by_id) == {"impact", "no-flaky-tests"}
    # Each carries its governance tags and the selector it bound through.
    assert by_id["no-flaky-tests"]["kind"] == "structural"
    assert by_id["no-flaky-tests"]["measures"] == "health"
    assert by_id["impact"]["kind"] == "human_dependent"
    selector = by_id["impact"]["selector"]
    assert isinstance(selector, str) and "repo=checkout" in selector
    assert all(r["enabled"] for r in rows)


def test_disabling_a_safeguard_drops_its_ceiling_from_the_score() -> None:
    # Catastrophic blast radius normally caps the float at 0. Toggle impact off and its ceiling no
    # longer reaches the scorer, so a healthy flakiness + full budget lifts the float back up.
    features = scenario.assemble_features(
        flakiness=0.0, services_affected=100.0, remaining_budget=1.0
    )
    assert scenario.scoring_function().score(features) == 0.0
    lifted = scenario.scoring_function({"impact"}).score(features)
    assert lifted == 0.9  # only no-flaky (0.9) and the full budget remain


def test_disabled_safeguard_still_lists_but_marked_off() -> None:
    rows = scenario.safeguard_panel({"impact"})
    by_id = {r["id"]: r for r in rows}
    assert by_id["impact"]["enabled"] is False
    assert by_id["no-flaky-tests"]["enabled"] is True


def test_ceiling_breakdown_drops_a_disabled_safeguards_row() -> None:
    features = scenario.assemble_features(
        flakiness=0.004, services_affected=1.0, remaining_budget=1.0
    )
    ids = {r["id"] for r in scenario.ceiling_breakdown(features, {"impact"})}
    assert ids == {"no-flaky-tests", "remaining-budget"}  # impact's row is gone


def test_leaf_inherits_the_parent_budget_when_no_override() -> None:
    # With no leaf override, the demo leaf resolves to the parent (root) budget verbatim.
    assert scenario.resolved_budget(parent_remaining=0.6, override=False) == 0.6


def test_leaf_override_wins_over_the_inherited_parent_budget() -> None:
    # Toggle the override on and the leaf's own budget wins, regardless of the parent value.
    resolved = scenario.resolved_budget(parent_remaining=0.9, override=True)
    assert resolved == scenario.LEAF_OVERRIDE_REMAINING


def test_tree_panel_shows_inheritance_then_override() -> None:
    inherited = {r["id"]: r for r in scenario.tree_panel(parent_remaining=0.6, override=False)}
    # Root declares the budget; the leaf inherits the same remaining value.
    assert inherited["ship-update"]["source"] == "declared"
    assert inherited["write-tests"]["source"] == "inherited"
    assert inherited["write-tests"]["remaining"] == 0.6
    assert inherited["write-tests"]["is_demo"] is True

    overridden = {r["id"]: r for r in scenario.tree_panel(parent_remaining=0.6, override=True)}
    # With the override on, the leaf now declares its own, tighter budget.
    assert overridden["write-tests"]["source"] == "declared"
    assert overridden["write-tests"]["remaining"] == scenario.LEAF_OVERRIDE_REMAINING


def test_current_flakiness_is_the_latest_ingested_health_signal() -> None:
    sink = scenario.seed_metrics()
    # The seed's newest health point (0.006) is the derived current signal.
    assert scenario.current_flakiness(sink) == 0.006


def test_ingesting_health_becomes_the_new_current_signal() -> None:
    sink = scenario.seed_metrics()
    scenario.ingest_measurement(sink, kind="health", value=0.018)
    assert scenario.current_flakiness(sink) == 0.018


def test_ingesting_efficacy_leaves_the_health_signal_untouched() -> None:
    sink = scenario.seed_metrics()
    before = scenario.current_flakiness(sink)
    scenario.ingest_measurement(sink, kind="efficacy", value=0.5)
    # Efficacy lands in its own series; the health signal that drives the score is unchanged.
    assert scenario.current_flakiness(sink) == before


def test_evidence_panel_keeps_health_and_efficacy_separate() -> None:
    panel = scenario.evidence_panel(scenario.seed_metrics())
    assert panel["safeguard_id"] == "no-flaky-tests"
    health, efficacy = panel["health"], panel["efficacy"]
    assert isinstance(health, dict) and isinstance(efficacy, dict)
    assert health["measures"] == "health"
    assert efficacy["measures"] == "efficacy"
    # Each series names its own kind's metric — never the other's.
    assert health["metric"] == "flakiness"
    assert efficacy["metric"] == "catch_rate"
    # Only the governing health series has a ceiling on the float.
    assert health["ceiling"] is not None
    assert efficacy["ceiling"] is None
    assert health["current"] == 0.006


def test_pipeline_runs_the_real_selector_classifier() -> None:
    rows = scenario.classified_pipeline()
    by_input = {r["input"]: r for r in rows}
    assert by_input["src/cart.test.ts"]["action_id"] == "write-tests"
    assert by_input["src/cart.ts"]["action_id"] == "write-code"
    assert by_input["npm test"]["resolved"] is False  # no rule matches a bare test run
