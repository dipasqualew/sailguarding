"""The framework-free request router behind the activity-model editor.

Kept as a pure ``(method, path, query, body) -> Response`` function so the whole surface is testable
without opening a socket: a test constructs an :class:`App` with an injected
:class:`~sailguarding.model.InMemoryActivityModelStore` and calls :meth:`App.handle` directly. The
:mod:`.server` module is the only place that touches ``http.server``.

Every mutation runs through one of the :class:`~sailguarding.model.ActivityModel`'s pure,
value-returning transforms — apply it, hold the new model, persist it to the injected store, and
return the refreshed view model — so the editor is a genuine front-end over the real aggregate, not
a re-implementation of it. Bad input never 500s: a malformed body or a transform's :class:`KeyError`
degrades to a 400 with an ``{"error": ...}`` payload.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

from sailguarding.model import (
    ActivityModel,
    ContextScope,
    FileWorkspaceStore,
    ImportKind,
    InMemoryWorkspaceStore,
    Workspace,
    WorkspaceStore,
)
from sailguarding.model.model import ROOT_ID
from sailguarding.safeguards import Measurement, SafeguardKind
from sailguarding.web import scenario
from sailguarding.web.page import render_page


def store_backed_workspace_store() -> WorkspaceStore | None:
    """A durable :class:`FileWorkspaceStore` under the configured store root, or ``None``.

    Mirrors the sensor's own store resolution: the same
    :class:`~sailguarding.sensor.config.SensorConfig` the hook resolves picks the root (under the
    git dir by default), and the workspace lives in ``workspace.json`` there. Kept fail-soft — a
    non-git directory, a permissions error, any storage failure yields ``None`` so the caller falls
    back to an in-memory store rather than breaking the server.
    """
    try:
        from sailguarding.sensor.cli import ENV_PROJECT_DIR
        from sailguarding.sensor.config import SensorConfig, resolve_store_root
        from sailguarding.sensor.pluginconfig import load_from_env
        from sailguarding.storage.git import SubprocessGitRunner

        env = os.environ
        repo = Path(env.get(ENV_PROJECT_DIR) or Path.cwd())
        git = SubprocessGitRunner(repo)
        config = SensorConfig.resolve(repo, env, load_from_env(env))
        root = resolve_store_root(git, repo, config.store_path)
        root.mkdir(parents=True, exist_ok=True)
        return FileWorkspaceStore(root / "workspace.json")
    except Exception:
        return None


@dataclass(frozen=True)
class Response:
    """A rendered HTTP response: status, content type, and body bytes."""

    status: int
    content_type: str
    body: bytes


class App:
    """Holds the :class:`Workspace` and routes requests that read or mutate it.

    On construction the workspace is loaded from the injected store; an empty store is seeded with
    :func:`scenario.seed_workspace` and saved, so a fresh instance always opens onto the starter
    models. Every mutation applies a pure transform, swaps in the new workspace, and persists it, so
    a second :class:`App` built on the same store sees the change.

    Model-level routes (``/api/model/*``) act on the workspace; activity/risk/safeguard/mitigation
    routes act on the **active** model within it — the same transforms the single-model editor used,
    now scoped to whichever model the switcher has selected.

    :param store: Where the workspace is loaded from and saved to. Defaults to a fresh
        :class:`InMemoryWorkspaceStore` — the injectable, no-I/O unit-test default.
    """

    def __init__(self, store: WorkspaceStore | None = None) -> None:
        self._store: WorkspaceStore = store or InMemoryWorkspaceStore()
        workspace = self._store.load()
        if workspace is None:
            workspace = scenario.seed_workspace()
            self._store.save(workspace)
        self._workspace = workspace

    @property
    def workspace(self) -> Workspace:
        return self._workspace

    @property
    def model(self) -> ActivityModel | None:
        """The active model — a convenience for callers that only care about the current model."""
        return self._workspace.active()

    def view_model(self) -> dict[str, Any]:
        """The JSON the UI renders — the workspace and its active model (see :func:`view_model`)."""
        return view_model(self._workspace)

    def handle(self, method: str, path: str, query: str = "", body: bytes = b"") -> Response:
        """Route one request. ``GET`` reads; ``POST`` mutates; everything else is a 405."""
        if method == "GET":
            return self._get(path)
        if method == "POST":
            return self._post(path, body)
        return _json({"error": f"method {method} not allowed"}, status=405)

    def _get(self, path: str) -> Response:
        if path == "/":
            html = render_page(self.view_model())
            return Response(200, "text/html; charset=utf-8", html.encode("utf-8"))
        if path == "/api/model":
            return _json(self.view_model())
        return _json({"error": f"not found: {path}"}, status=404)

    def _post(self, path: str, body: bytes) -> Response:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return _json({"error": "request body must be valid JSON"}, status=400)
        if not isinstance(payload, dict):
            return _json({"error": "request body must be a JSON object"}, status=400)

        try:
            outcome = self._apply(path, payload)
        except KeyError as exc:
            return _json({"error": exc.args[0] if exc.args else str(exc)}, status=400)
        except (ValueError, TypeError) as exc:
            return _json({"error": str(exc)}, status=400)

        if outcome is None:
            return _json({"error": f"not found: {path}"}, status=404)

        workspace, created_id = outcome
        self._workspace = workspace
        self._store.save(workspace)
        return _json({"model": self.view_model(), "created_id": created_id})

    def _apply(self, path: str, payload: dict[str, Any]) -> tuple[Workspace, str | None] | None:
        """Apply the mutation named by ``path``. ``None`` means the path is unknown (a 404).

        Returns ``(new_workspace, created_id)``; ``created_id`` is the fresh id for creating routes
        and ``None`` otherwise. Missing or wrong-typed fields raise :class:`ValueError`; missing
        references raise :class:`KeyError` — both become 400s upstream.
        """
        model_route = self._apply_model(path, payload)
        if model_route is not None:
            return model_route
        return self._apply_active(path, payload)

    def _apply_model(
        self, path: str, payload: dict[str, Any]
    ) -> tuple[Workspace, str | None] | None:
        """Workspace-level routes: create, rename, delete, select, scope, and cross-model import."""
        ws = self._workspace
        if path == "/api/model/add":
            return ws.add_model(_str(payload, "name"))
        if path == "/api/model/rename":
            return ws.rename_model(_str(payload, "id"), _str(payload, "name")), None
        if path == "/api/model/delete":
            return ws.remove_model(_str(payload, "id")), None
        if path == "/api/model/select":
            return ws.select(_str(payload, "id")), None
        if path == "/api/model/scope/set":
            model = ws.find(_str(payload, "id"))
            if model is None:
                raise KeyError(f"no model {payload.get('id')!r} in workspace")
            scope = _scope(payload)
            return ws.replace_model(model.set_applies_when(scope)), None
        if path == "/api/model/import":
            return ws.import_into(
                _str(payload, "target_id"),
                _str(payload, "source_id"),
                _import_kind(payload),
                _str(payload, "entity_id"),
                _opt_str(payload, "parent_id"),
            )
        return None

    def _apply_active(
        self, path: str, payload: dict[str, Any]
    ) -> tuple[Workspace, str | None] | None:
        """Active-model routes: the activity/risk/safeguard/mitigation transforms."""
        known = {
            "/api/activity/add",
            "/api/activity/rename",
            "/api/activity/delete",
            "/api/risk/create",
            "/api/activity/risk/attach",
            "/api/activity/risk/detach",
            "/api/safeguard/create",
            "/api/mitigation/add",
            "/api/mitigation/remove",
        }
        if path not in known:
            return None
        model = self._workspace.active()
        if model is None:
            raise KeyError("no active model to edit")

        created_id: str | None = None
        if path == "/api/activity/add":
            model, created_id = model.add_activity(
                _opt_str(payload, "parent_id"), _str(payload, "label")
            )
        elif path == "/api/activity/rename":
            model = model.rename_activity(_str(payload, "id"), _str(payload, "label"))
        elif path == "/api/activity/delete":
            model = model.remove_activity(_str(payload, "id"))
        elif path == "/api/risk/create":
            model, created_id = model.add_risk(
                _str(payload, "label"), _opt_str(payload, "description") or ""
            )
        elif path == "/api/activity/risk/attach":
            model = model.attach_risk(_str(payload, "activity_id"), _str(payload, "risk_id"))
        elif path == "/api/activity/risk/detach":
            model = model.detach_risk(_str(payload, "activity_id"), _str(payload, "risk_id"))
        elif path == "/api/safeguard/create":
            model, created_id = model.add_safeguard(
                _str(payload, "label"),
                SafeguardKind(_str(payload, "kind")),
                Measurement(_str(payload, "measures")),
                _opt_str(payload, "metric") or "",
                _cadence(payload),
            )
        elif path == "/api/mitigation/add":
            model = model.add_mitigation(
                _str(payload, "activity_id"),
                _str(payload, "risk_id"),
                _str(payload, "safeguard_id"),
            )
        elif path == "/api/mitigation/remove":
            model = model.remove_mitigation(
                _str(payload, "activity_id"),
                _str(payload, "risk_id"),
                _str(payload, "safeguard_id"),
            )
        return self._workspace.replace_model(model), created_id


def view_model(workspace: Workspace) -> dict[str, Any]:
    """Flatten a :class:`Workspace` into the JSON shape the editor renders.

    The top level carries the **model switcher** — ``models`` (each with its id, name, applicability
    scope, and headline counts) and the ``active_id`` — plus the **active model's** own flattened
    view (``activities``/``risks``/``safeguards``/edges and ``applies_when``), so the existing panes
    read the active model exactly as before while the header can navigate between models.
    """
    active = workspace.active()
    payload: dict[str, Any] = {
        "models": [_model_summary(m) for m in workspace.models],
        "active_id": workspace.active_id,
    }
    payload.update(model_view(active))
    return payload


def _model_summary(model: ActivityModel) -> dict[str, Any]:
    """A model's header entry: name, scope, headline counts, and pick-lists for the import dialog.

    The pick-lists (``activities``/``risks``/``safeguards`` as id + label) let the client offer a
    *source* model's entities in the import dialog without a second round-trip — the whole workspace
    travels in one payload.
    """
    activities: list[dict[str, Any]] = []
    for top in model.top_level():
        _pick_activities(top, 0, activities)
    return {
        "id": model.id,
        "name": model.name,
        "applies_when": _applies_when_dict(model.applies_when),
        "activity_count": len(activities),
        "risk_count": len(model.risks),
        "safeguard_count": len(model.safeguards),
        "activities": activities,
        "risks": [{"id": r.id, "label": r.label} for r in model.risks],
        "safeguards": [
            {"id": s.id, "label": s.label, "kind": s.kind.value, "measures": s.measures.value}
            for s in model.safeguards
        ],
    }


def _pick_activities(node: Any, depth: int, out: list[dict[str, Any]]) -> None:
    """Collect ``{id, label, depth}`` for a subtree — the import dialog's activity picker source."""
    out.append({"id": node.id, "label": node.label, "depth": depth})
    for child in node.children:
        _pick_activities(child, depth + 1, out)


def model_view(model: ActivityModel | None) -> dict[str, Any]:
    """The active model's flattened view — activities, libraries, edges, and applicability.

    Activities come back depth-first with the synthetic root excluded, each carrying its depth,
    child ids, and the counts (risks faced, mitigation edges) the birds-eye tree reads. Risks and
    safeguards carry their reuse count (``used_by`` = distinct activities referencing them). Returns
    empty collections when there is no active model (an empty workspace).
    """
    if model is None:
        return {
            "activities": [],
            "risks": [],
            "safeguards": [],
            "activity_risks": [],
            "mitigations": [],
            "applies_when": _applies_when_dict(ContextScope.empty()),
        }
    activities: list[dict[str, Any]] = []
    for top in model.top_level():
        _flatten(model, top, 0, activities)

    risks = [
        {
            "id": risk.id,
            "label": risk.label,
            "description": risk.description,
            "used_by": len(model.activities_using_risk(risk.id)),
        }
        for risk in model.risks
    ]
    safeguards = [
        {
            "id": sg.id,
            "label": sg.label,
            "kind": sg.kind.value,
            "measures": sg.measures.value,
            "metric": sg.metric,
            "cadence_seconds": (sg.cadence.total_seconds() if sg.cadence is not None else None),
            "used_by": len(model.activities_using_safeguard(sg.id)),
        }
        for sg in model.safeguards
    ]
    return {
        "activities": activities,
        "risks": risks,
        "safeguards": safeguards,
        "activity_risks": sorted([a, r] for (a, r) in model.activity_risks),
        "mitigations": sorted([a, r, s] for (a, r, s) in model.mitigations),
        "applies_when": _applies_when_dict(model.applies_when),
    }


def _applies_when_dict(scope: ContextScope) -> dict[str, Any]:
    """The wire shape for an applicability scope: its dimensions plus a human summary."""
    return {
        "dimensions": [{"name": c.name, "values": list(c.values)} for c in scope.dimensions],
        "summary": scope.describe(),
    }


def _flatten(model: ActivityModel, node: Any, depth: int, out: list[dict[str, Any]]) -> None:
    parent = None if node.parent_id in (None, ROOT_ID) else node.parent_id
    mitigation_count = sum(1 for edge in model.mitigations if edge[0] == node.id)
    out.append(
        {
            "id": node.id,
            "label": node.label,
            "parent_id": parent,
            "depth": depth,
            "child_ids": [child.id for child in node.children],
            "risk_count": len(model.risks_for(node.id)),
            "mitigation_count": mitigation_count,
        }
    )
    for child in node.children:
        _flatten(model, child, depth + 1, out)


def _str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"field {key!r} must be a string")
    return value


def _opt_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"field {key!r} must be a string or null")
    return value


def _scope(payload: dict[str, Any]) -> ContextScope:
    """Build a :class:`ContextScope` from a ``{dimensions: [{name, values: [...]}]}`` payload.

    Order is preserved; a malformed dimension (missing/typed-wrong ``name`` or a non-list
    ``values``, or a non-string value) raises :class:`ValueError` and becomes a 400 upstream.
    """
    raw = payload.get("dimensions", [])
    if not isinstance(raw, list):
        raise ValueError("field 'dimensions' must be a list")
    scope = ContextScope.empty()
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("each dimension must be an object")
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("each dimension needs a non-empty 'name'")
        values = entry.get("values", [])
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ValueError(f"dimension {name!r} 'values' must be a list of strings")
        scope = scope.set_dimension(name, values)
    return scope


def _import_kind(payload: dict[str, Any]) -> ImportKind:
    """Read and validate the import ``kind`` (``activity`` / ``risk`` / ``safeguard``)."""
    kind = _str(payload, "kind")
    if kind not in ("activity", "risk", "safeguard"):
        raise ValueError(f"unknown import kind {kind!r}")
    return cast(ImportKind, kind)


def _cadence(payload: dict[str, Any]) -> timedelta | None:
    value = payload.get("cadence_seconds")
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("field 'cadence_seconds' must be a number or null")
    return timedelta(seconds=float(value))


def _json(payload: object, *, status: int = 200) -> Response:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return Response(status, "application/json; charset=utf-8", body)
