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


def test_pipeline_runs_the_real_selector_classifier() -> None:
    rows = scenario.classified_pipeline()
    by_input = {r["input"]: r for r in rows}
    assert by_input["src/cart.test.ts"]["action_id"] == "write-tests"
    assert by_input["src/cart.ts"]["action_id"] == "write-code"
    assert by_input["npm test"]["resolved"] is False  # no rule matches a bare test run
