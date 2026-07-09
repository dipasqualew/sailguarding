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


# -- seed_workspace ---------------------------------------------------------------------------


def test_seed_workspace_has_three_models_with_product_active() -> None:
    ws = scenario.seed_workspace()
    assert ws.model_ids() == (
        "product-software-engineering",
        "platform-software-engineering",
        "sales",
    )
    active = ws.active()
    assert active is not None
    assert active.id == "product-software-engineering"
    assert active.name == "Product Software Engineering"


def test_seed_workspace_model_names() -> None:
    ws = scenario.seed_workspace()
    names = {m.id: m.name for m in ws.models}
    assert names == {
        "product-software-engineering": "Product Software Engineering",
        "platform-software-engineering": "Platform Software Engineering",
        "sales": "Sales",
    }


def test_seed_workspace_products_applies_when_scopes_the_repos() -> None:
    product = scenario.seed_workspace().find("product-software-engineering")
    assert product is not None
    assert product.applies_when.describe() == "repo ∈ {checkout, billing}"


def test_seed_workspace_sales_is_scoped_to_the_team() -> None:
    sales = scenario.seed_workspace().find("sales")
    assert sales is not None
    assert sales.applies_when.describe() == "team = sales"


def test_platform_shares_the_ephemeral_environments_safeguard_id_with_product() -> None:
    ws = scenario.seed_workspace()
    product = ws.find("product-software-engineering")
    platform = ws.find("platform-software-engineering")
    assert product is not None and platform is not None
    assert product.find_safeguard("ephemeral-environments") is not None
    assert platform.find_safeguard("ephemeral-environments") is not None


def test_seed_workspace_round_trips_through_json() -> None:
    from sailguarding.model import Workspace

    ws = scenario.seed_workspace()
    assert Workspace.from_json(ws.to_json()) == ws
