"""The demo scenario builds a real ActivityModel through the aggregate's own transforms."""

from __future__ import annotations

from sailguarding.model.model import ROOT_ID
from sailguarding.web import scenario


def test_seed_model_has_the_starter_activity_tree() -> None:
    model = scenario.seed_model()
    tops = model.top_level()
    assert [a.label for a in tops] == ["Develop new capabilities"]
    develop = tops[0]
    assert [c.label for c in develop.children] == ["Write software", "Test software"]
    # The synthetic root is never surfaced as a top-level activity.
    assert all(a.id != ROOT_ID for a in tops)


def test_seed_model_populates_the_risk_and_safeguard_libraries() -> None:
    model = scenario.seed_model()
    assert {r.label for r in model.risks} == {"Break capabilities", "Data loss", "Opportunity cost"}
    assert {s.label for s in model.safeguards} == {"Human code reviews", "Ephemeral environments"}


def test_shared_safeguard_covers_a_risk_on_two_activities() -> None:
    model = scenario.seed_model()
    reviews = next(s for s in model.safeguards if s.label == "Human code reviews")
    # The reuse story: one safeguard mitigating the same risk across two distinct activities.
    assert len(model.activities_using_safeguard(reviews.id)) == 2


def test_shared_risk_is_faced_by_two_activities() -> None:
    model = scenario.seed_model()
    break_caps = next(r for r in model.risks if r.label == "Break capabilities")
    assert len(model.activities_using_risk(break_caps.id)) == 2


def test_seed_model_round_trips() -> None:
    model = scenario.seed_model()
    from sailguarding.model import ActivityModel

    assert ActivityModel.from_json(model.to_json()) == model
