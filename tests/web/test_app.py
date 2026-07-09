"""The activity-model editor router: real ActivityModel transforms over HTTP shapes.

Every test injects a fresh :class:`InMemoryActivityModelStore`, so there is no I/O and nothing is
shared between cases — the model round-trips through its serialised form on each save.
"""

from __future__ import annotations

import json
from typing import Any

from sailguarding.model import InMemoryWorkspaceStore
from sailguarding.web import App
from sailguarding.web.app import Response


def _app() -> App:
    return App(InMemoryWorkspaceStore())


def _post(app: App, path: str, body: dict[str, Any]) -> Response:
    return app.handle("POST", path, "", json.dumps(body).encode("utf-8"))


def _json(response: Response) -> dict[str, Any]:
    assert response.content_type.startswith("application/json")
    data: dict[str, Any] = json.loads(response.body)
    return data


def _model(response: Response) -> dict[str, Any]:
    data = _json(response)
    assert response.status == 200, data
    model = data["model"]
    assert isinstance(model, dict)
    return model


def _view(app: App) -> dict[str, Any]:
    return _json(app.handle("GET", "/api/model"))


def _find(items: list[dict[str, Any]], label: str) -> dict[str, Any]:
    return next(i for i in items if i["label"] == label)


# --- Reads --------------------------------------------------------------------------------------


def test_index_serves_a_populated_html_page() -> None:
    response = _app().handle("GET", "/")
    assert response.status == 200
    assert response.content_type.startswith("text/html")
    body = response.body.decode("utf-8")
    assert "window.__MODEL__" in body
    assert "__MODEL_JSON__" not in body  # the token is filled
    # The seed model reaches the page so the first paint is populated.
    assert "Develop new capabilities" in body
    assert "Human code reviews" in body


def test_api_model_returns_the_seeded_view_model() -> None:
    view = _view(_app())
    assert {"activities", "risks", "safeguards", "activity_risks", "mitigations"} <= set(view)
    labels = [a["label"] for a in view["activities"]]
    assert labels == ["Develop new capabilities", "Write software", "Test software"]
    # Top-level activity has a null parent and depth 0; children carry their parent and depth 1.
    develop = _find(view["activities"], "Develop new capabilities")
    assert develop["parent_id"] is None and develop["depth"] == 0
    write = _find(view["activities"], "Write software")
    assert write["parent_id"] == develop["id"] and write["depth"] == 1


def test_view_model_reports_reuse_counts() -> None:
    view = _view(_app())
    reviews = _find(view["safeguards"], "Human code reviews")
    assert reviews["used_by"] == 2  # the shared safeguard covers two activities
    break_caps = _find(view["risks"], "Break capabilities")
    assert break_caps["used_by"] == 2


def test_view_model_reports_per_activity_counts() -> None:
    write = _find(_view(_app())["activities"], "Write software")
    # Write software faces Break capabilities + Data loss, and has two mitigation edges.
    assert write["risk_count"] == 2
    assert write["mitigation_count"] == 2


# --- Mutations ----------------------------------------------------------------------------------


def test_add_activity_creates_a_child_and_returns_its_id() -> None:
    app = _app()
    develop = _find(_view(app)["activities"], "Develop new capabilities")
    data = _json(_post(app, "/api/activity/add", {"parent_id": develop["id"], "label": "Ship it"}))
    created = data["created_id"]
    assert isinstance(created, str) and created
    child = next(a for a in data["model"]["activities"] if a["id"] == created)
    assert child["label"] == "Ship it" and child["parent_id"] == develop["id"]


def test_add_top_level_activity_with_null_parent() -> None:
    app = _app()
    model = _model(_post(app, "/api/activity/add", {"parent_id": None, "label": "New root"}))
    new = _find(model["activities"], "New root")
    assert new["parent_id"] is None and new["depth"] == 0


def test_rename_activity() -> None:
    app = _app()
    write = _find(_view(app)["activities"], "Write software")
    model = _model(
        _post(app, "/api/activity/rename", {"id": write["id"], "label": "Author software"})
    )
    renamed = next(a for a in model["activities"] if a["id"] == write["id"])
    assert renamed["label"] == "Author software"


def test_delete_activity_cascades_its_risk_and_mitigation_edges() -> None:
    app = _app()
    write = _find(_view(app)["activities"], "Write software")
    model = _model(_post(app, "/api/activity/delete", {"id": write["id"]}))
    ids = {a["id"] for a in model["activities"]}
    assert write["id"] not in ids
    # No dangling edges to the removed activity remain.
    assert all(e[0] != write["id"] for e in model["activity_risks"])
    assert all(e[0] != write["id"] for e in model["mitigations"])


def test_create_risk_then_attach_and_detach() -> None:
    app = _app()
    develop = _find(_view(app)["activities"], "Develop new capabilities")
    created = _json(_post(app, "/api/risk/create", {"label": "Regulatory breach"}))
    rid = created["created_id"]
    assert isinstance(rid, str)

    attached = _model(
        _post(app, "/api/activity/risk/attach", {"activity_id": develop["id"], "risk_id": rid})
    )
    assert [develop["id"], rid] in attached["activity_risks"]

    detached = _model(
        _post(app, "/api/activity/risk/detach", {"activity_id": develop["id"], "risk_id": rid})
    )
    assert [develop["id"], rid] not in detached["activity_risks"]


def test_create_safeguard_carries_kind_and_measures() -> None:
    app = _app()
    created = _json(
        _post(
            app,
            "/api/safeguard/create",
            {"label": "Spend cap", "kind": "structural", "measures": "health", "metric": "usd"},
        )
    )
    sid = created["created_id"]
    sg = _find(created["model"]["safeguards"], "Spend cap")
    assert sg["id"] == sid
    assert sg["kind"] == "structural" and sg["measures"] == "health" and sg["metric"] == "usd"


def test_mitigation_add_and_remove() -> None:
    app = _app()
    view = _view(app)
    write = _find(view["activities"], "Write software")
    opp = _find(view["risks"], "Opportunity cost")
    reviews = _find(view["safeguards"], "Human code reviews")
    # A mitigation needs the risk on the activity first.
    _post(app, "/api/activity/risk/attach", {"activity_id": write["id"], "risk_id": opp["id"]})
    added = _model(
        _post(
            app,
            "/api/mitigation/add",
            {"activity_id": write["id"], "risk_id": opp["id"], "safeguard_id": reviews["id"]},
        )
    )
    assert [write["id"], opp["id"], reviews["id"]] in added["mitigations"]

    removed = _model(
        _post(
            app,
            "/api/mitigation/remove",
            {"activity_id": write["id"], "risk_id": opp["id"], "safeguard_id": reviews["id"]},
        )
    )
    assert [write["id"], opp["id"], reviews["id"]] not in removed["mitigations"]


def test_shared_safeguard_reaches_used_by_two_via_the_api() -> None:
    # Assign one fresh safeguard to a risk on two different activities; its reuse count reads 2.
    app = _app()
    view = _view(app)
    write = _find(view["activities"], "Write software")
    test = _find(view["activities"], "Test software")
    data_loss = _find(view["risks"], "Data loss")

    sg = _json(
        _post(
            app,
            "/api/safeguard/create",
            {"label": "Backups", "kind": "structural", "measures": "health"},
        )
    )
    sid = sg["created_id"]
    # Data loss already faces Write; attach it to Test too, then mitigate both with Backups.
    _post(app, "/api/activity/risk/attach", {"activity_id": test["id"], "risk_id": data_loss["id"]})
    _post(
        app,
        "/api/mitigation/add",
        {"activity_id": write["id"], "risk_id": data_loss["id"], "safeguard_id": sid},
    )
    final = _model(
        _post(
            app,
            "/api/mitigation/add",
            {"activity_id": test["id"], "risk_id": data_loss["id"], "safeguard_id": sid},
        )
    )
    backups = _find(final["safeguards"], "Backups")
    assert backups["used_by"] == 2


# --- Workspace: the model switcher --------------------------------------------------------------


def test_view_model_exposes_the_workspace_models_and_active_id() -> None:
    view = _view(_app())
    models = {m["id"]: m for m in view["models"]}
    assert set(models) == {
        "product-software-engineering",
        "platform-software-engineering",
        "sales",
    }
    assert view["active_id"] == "product-software-engineering"
    # The active model's applicability travels at the top level too.
    assert view["applies_when"]["summary"] == "repo ∈ {checkout, billing}"
    assert models["product-software-engineering"]["applies_when"]["summary"] == (
        "repo ∈ {checkout, billing}"
    )


def test_each_model_summary_carries_pick_lists_and_counts() -> None:
    product = next(m for m in _view(_app())["models"] if m["id"] == "product-software-engineering")
    assert product["name"] == "Product Software Engineering"
    assert product["activity_count"] == len(product["activities"]) == 3
    assert {a["label"] for a in product["activities"]} == {
        "Develop new capabilities",
        "Write software",
        "Test software",
    }
    assert {r["label"] for r in product["risks"]} == {
        "Break capabilities",
        "Data loss",
        "Opportunity cost",
    }
    assert {s["label"] for s in product["safeguards"]} == {
        "Human code reviews",
        "Ephemeral environments",
    }


def test_select_switches_the_active_model_and_its_view() -> None:
    app = _app()
    model = _model(_post(app, "/api/model/select", {"id": "sales"}))
    view = app.view_model()
    assert view["active_id"] == "sales"
    labels = [a["label"] for a in model["activities"]]
    assert labels == ["Close new business", "Qualify the lead", "Send the proposal"]


def test_select_unknown_model_is_400() -> None:
    assert _post(_app(), "/api/model/select", {"id": "nope"}).status == 400


def test_add_model_creates_and_activates_it() -> None:
    app = _app()
    data = _json(_post(app, "/api/model/add", {"name": "Support"}))
    created = data["created_id"]
    assert created == "support"
    assert data["model"]["active_id"] == "support"
    assert any(m["id"] == "support" for m in data["model"]["models"])
    # The freshly created model is empty.
    assert data["model"]["activities"] == []


def test_rename_model() -> None:
    app = _app()
    model = _model(_post(app, "/api/model/rename", {"id": "sales", "name": "Revenue"}))
    sales = next(m for m in model["models"] if m["id"] == "sales")
    assert sales["name"] == "Revenue"


def test_delete_model_removes_it() -> None:
    app = _app()
    model = _model(_post(app, "/api/model/delete", {"id": "sales"}))
    assert all(m["id"] != "sales" for m in model["models"])


def test_scope_set_updates_a_models_applies_when() -> None:
    app = _app()
    model = _model(
        _post(
            app,
            "/api/model/scope/set",
            {"id": "sales", "dimensions": [{"name": "team", "values": ["sales", "growth"]}]},
        )
    )
    sales = next(m for m in model["models"] if m["id"] == "sales")
    assert sales["applies_when"]["summary"] == "team ∈ {sales, growth}"


def test_scope_set_with_a_bad_dimension_is_400() -> None:
    app = _app()
    # A dimension missing its name is a client error, not a crash.
    bad_name = _post(
        app, "/api/model/scope/set", {"id": "sales", "dimensions": [{"values": ["x"]}]}
    )
    assert bad_name.status == 400
    # Non-list values is likewise a 400.
    bad_values = _post(
        app,
        "/api/model/scope/set",
        {"id": "sales", "dimensions": [{"name": "team", "values": "sales"}]},
    )
    assert bad_values.status == 400


def test_import_copies_an_activity_from_platform_into_product() -> None:
    app = _app()
    view = _view(app)
    platform = next(m for m in view["models"] if m["id"] == "platform-software-engineering")
    operate = _find(platform["activities"], "Operate the platform")
    before = platform["activity_count"]

    data = _json(
        _post(
            app,
            "/api/model/import",
            {
                "target_id": "product-software-engineering",
                "source_id": "platform-software-engineering",
                "kind": "activity",
                "entity_id": operate["id"],
            },
        )
    )
    created = data["created_id"]  # the new activity id in the target model
    assert isinstance(created, str) and created
    # Product (the active model) gained a top-level activity.
    top_labels = [a["label"] for a in data["model"]["activities"] if a["depth"] == 0]
    assert "Operate the platform" in top_labels
    # The source (platform) is untouched — same activity count as before.
    platform_after = next(
        m for m in data["model"]["models"] if m["id"] == "platform-software-engineering"
    )
    assert platform_after["activity_count"] == before


def test_import_unknown_kind_is_400() -> None:
    response = _post(
        _app(),
        "/api/model/import",
        {
            "target_id": "product-software-engineering",
            "source_id": "sales",
            "kind": "bogus",
            "entity_id": "whatever",
        },
    )
    assert response.status == 400


def test_active_model_route_mutates_only_the_active_model() -> None:
    app = _app()
    # Add a top-level activity to Product (the active model).
    _post(app, "/api/activity/add", {"parent_id": None, "label": "Extra activity"})
    view = app.view_model()
    product = next(m for m in view["models"] if m["id"] == "product-software-engineering")
    sales = next(m for m in view["models"] if m["id"] == "sales")
    assert any(a["label"] == "Extra activity" for a in product["activities"])
    # Sales, which was not active, is unchanged.
    assert all(a["label"] != "Extra activity" for a in sales["activities"])


# --- Persistence --------------------------------------------------------------------------------


def test_mutation_is_persisted_to_the_injected_store() -> None:
    store = InMemoryWorkspaceStore()
    app = App(store)
    _post(app, "/api/activity/add", {"parent_id": None, "label": "Persisted root"})
    # A second App on the same store sees the change — it was saved, not just held in memory.
    reopened = App(store)
    labels = [a["label"] for a in reopened.view_model()["activities"]]
    assert "Persisted root" in labels


def test_empty_store_is_seeded_and_saved_on_construction() -> None:
    store = InMemoryWorkspaceStore()
    App(store)
    assert store.load() is not None  # seeding persisted the starter workspace


# --- Fail-soft error handling -------------------------------------------------------------------


def test_unknown_path_is_404() -> None:
    assert _app().handle("GET", "/nope").status == 404
    assert _app().handle("POST", "/api/nope", "", b"{}").status == 404


def test_non_get_or_post_method_is_405() -> None:
    assert _app().handle("DELETE", "/api/model").status == 405


def test_malformed_body_is_400() -> None:
    app = _app()
    assert app.handle("POST", "/api/activity/add", "", b"not json").status == 400
    assert app.handle("POST", "/api/activity/add", "", b"[1,2,3]").status == 400  # not an object


def test_missing_field_is_400() -> None:
    # No label field — a client error, not a server crash.
    response = _post(_app(), "/api/activity/add", {"parent_id": None})
    assert response.status == 400
    assert "error" in _json(response)


def test_bad_reference_is_400_not_500() -> None:
    # A KeyError from the transform (unknown activity) degrades to a 400.
    response = _post(_app(), "/api/activity/rename", {"id": "does-not-exist", "label": "x"})
    assert response.status == 400
    assert "error" in _json(response)


def test_bad_enum_value_is_400() -> None:
    response = _post(
        _app(), "/api/safeguard/create", {"label": "X", "kind": "bogus", "measures": "health"}
    )
    assert response.status == 400
