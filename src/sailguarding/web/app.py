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
from typing import Any

from sailguarding.model import (
    ActivityModel,
    ActivityModelStore,
    FileActivityModelStore,
    InMemoryActivityModelStore,
)
from sailguarding.model.model import ROOT_ID
from sailguarding.safeguards import Measurement, SafeguardKind
from sailguarding.web import scenario
from sailguarding.web.page import render_page


def store_backed_model_store() -> ActivityModelStore | None:
    """A durable :class:`FileActivityModelStore` under the configured store root, or ``None``.

    Mirrors the sensor's own store resolution: the same
    :class:`~sailguarding.sensor.config.SensorConfig` the hook resolves picks the root (under the
    git dir by default), and the model lives in ``model.json`` there. Kept fail-soft — a non-git
    directory, a permissions error, any storage failure yields ``None`` so the caller falls back to
    an in-memory store rather than breaking the server.
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
        return FileActivityModelStore(root / "model.json")
    except Exception:
        return None


@dataclass(frozen=True)
class Response:
    """A rendered HTTP response: status, content type, and body bytes."""

    status: int
    content_type: str
    body: bytes


class App:
    """Holds the current :class:`ActivityModel` and routes requests that read or mutate it.

    On construction the model is loaded from the injected store; an empty store is seeded with
    :func:`scenario.seed_model` and saved, so a fresh instance always opens onto the starter model.
    Every mutation applies a pure transform, swaps in the new model, and persists it, so a second
    :class:`App` built on the same store sees the change.

    :param store: Where the model is loaded from and saved to. Defaults to a fresh
        :class:`InMemoryActivityModelStore` — the injectable, no-I/O unit-test default.
    """

    def __init__(self, store: ActivityModelStore | None = None) -> None:
        self._store: ActivityModelStore = store or InMemoryActivityModelStore()
        model = self._store.load()
        if model is None:
            model = scenario.seed_model()
            self._store.save(model)
        self._model = model

    @property
    def model(self) -> ActivityModel:
        return self._model

    def view_model(self) -> dict[str, Any]:
        """The JSON the UI renders — the model flattened for the wire (see :func:`view_model`)."""
        return view_model(self._model)

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

        model, created_id = outcome
        self._model = model
        self._store.save(model)
        return _json({"model": self.view_model(), "created_id": created_id})

    def _apply(self, path: str, payload: dict[str, Any]) -> tuple[ActivityModel, str | None] | None:
        """Apply the mutation named by ``path``. ``None`` means the path is unknown (a 404).

        Returns ``(new_model, created_id)``; ``created_id`` is the fresh id for creating routes and
        ``None`` for edge/rename/delete routes. Missing or wrong-typed fields raise
        :class:`ValueError`; missing references raise :class:`KeyError` — both become 400s upstream.
        """
        model = self._model
        if path == "/api/activity/add":
            return model.add_activity(_opt_str(payload, "parent_id"), _str(payload, "label"))
        if path == "/api/activity/rename":
            return model.rename_activity(_str(payload, "id"), _str(payload, "label")), None
        if path == "/api/activity/delete":
            return model.remove_activity(_str(payload, "id")), None
        if path == "/api/risk/create":
            return model.add_risk(_str(payload, "label"), _opt_str(payload, "description") or "")
        if path == "/api/activity/risk/attach":
            return model.attach_risk(_str(payload, "activity_id"), _str(payload, "risk_id")), None
        if path == "/api/activity/risk/detach":
            return model.detach_risk(_str(payload, "activity_id"), _str(payload, "risk_id")), None
        if path == "/api/safeguard/create":
            return model.add_safeguard(
                _str(payload, "label"),
                SafeguardKind(_str(payload, "kind")),
                Measurement(_str(payload, "measures")),
                _opt_str(payload, "metric") or "",
                _cadence(payload),
            )
        if path == "/api/mitigation/add":
            return (
                model.add_mitigation(
                    _str(payload, "activity_id"),
                    _str(payload, "risk_id"),
                    _str(payload, "safeguard_id"),
                ),
                None,
            )
        if path == "/api/mitigation/remove":
            return (
                model.remove_mitigation(
                    _str(payload, "activity_id"),
                    _str(payload, "risk_id"),
                    _str(payload, "safeguard_id"),
                ),
                None,
            )
        return None


def view_model(model: ActivityModel) -> dict[str, Any]:
    """Flatten an :class:`ActivityModel` into the JSON shape the editor renders.

    Activities come back depth-first with the synthetic root excluded, each carrying its depth,
    child ids, and the counts (risks faced, mitigation edges) the birds-eye tree reads. Risks and
    safeguards carry their reuse count (``used_by`` = distinct activities referencing them). The
    edge lists (``activity_risks``, ``mitigations``) are handed over flat and sorted; the JS joins
    them against the libraries to build per-activity detail.
    """
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
