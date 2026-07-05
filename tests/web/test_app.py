"""The demo router: real scoring, real classification, real decision log — over HTTP shapes."""

from __future__ import annotations

import json

import pytest

from sailguarding.web import App


def _score(app: App, **params: object) -> dict[str, object]:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    response = app.handle("GET", "/api/score", query)
    assert response.status == 200
    assert response.content_type.startswith("application/json")
    data: dict[str, object] = json.loads(response.body)
    return data


def test_index_serves_a_populated_html_page() -> None:
    response = App().handle("GET", "/")
    assert response.status == 200
    assert response.content_type.startswith("text/html")
    body = response.body.decode("utf-8")
    assert "window.__INITIAL__" in body
    # Every template token must be filled — no leftover placeholders in the served page.
    assert "__INITIAL_JSON__" not in body
    assert "__IMPACT_MAX__" not in body


def test_default_score_is_in_range_and_names_the_function() -> None:
    data = _score(App())
    assert 0.0 <= float(data["score"]) <= 1.0  # type: ignore[arg-type]
    assert data["function"] == {"name": "min-composition", "version": "1"}
    assert isinstance(data["ceilings"], list)


def test_impact_caps_hard() -> None:
    # A catastrophic blast radius ceilings the float at 0 no matter the other inputs.
    data = _score(App(), impact=100, flakiness=0, budget=1.0)
    assert data["score"] == 0.0
    assert data["binding"] == "Blast radius"


def test_budget_pulls_the_float_down() -> None:
    app = App()
    full = _score(app, impact=1, flakiness=0.004, budget=1.0)
    scarce = _score(app, impact=1, flakiness=0.004, budget=0.2)
    assert full["score"] == 0.9
    assert scarce["score"] == pytest.approx(0.2)
    assert scarce["binding"] == "Remaining budget"


def test_every_score_appends_to_the_decision_log() -> None:
    app = App()
    _score(app, impact=1, flakiness=0.004, budget=1.0)
    _score(app, impact=2, flakiness=0.004, budget=0.5)

    assert len(app.log) == 2
    decisions = json.loads(app.handle("GET", "/api/decisions").body)["decisions"]
    assert len(decisions) == 2
    assert decisions[0]["remaining_budget"] == pytest.approx(0.5)  # newest first
    assert decisions[0]["action_id"] == "write-tests"


def test_out_of_range_inputs_are_clamped() -> None:
    data = _score(App(), impact=999, flakiness=9, budget=5)
    # Clamped, not crashed: impact past the cap still ceilings hard; budget clamps to 1.
    assert 0.0 <= float(data["score"]) <= 1.0  # type: ignore[arg-type]


def test_pipeline_classifies_seed_events() -> None:
    data = json.loads(App().handle("GET", "/api/pipeline").body)
    events = data["events"]
    outcomes = {e["input"]: (e["outcome"], e["action_id"]) for e in events}
    assert outcomes["src/cart.test.ts"] == ("matched", "write-tests")
    assert outcomes["npm run deploy:staging"] == ("matched", "deploy")


def test_unknown_path_is_404_and_non_get_is_405() -> None:
    app = App()
    assert app.handle("GET", "/nope").status == 404
    assert app.handle("POST", "/api/score").status == 405
