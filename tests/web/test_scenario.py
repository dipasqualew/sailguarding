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


def test_pipeline_runs_the_real_selector_classifier() -> None:
    rows = scenario.classified_pipeline()
    by_input = {r["input"]: r for r in rows}
    assert by_input["src/cart.test.ts"]["action_id"] == "write-tests"
    assert by_input["src/cart.ts"]["action_id"] == "write-code"
    assert by_input["npm test"]["resolved"] is False  # no rule matches a bare test run
