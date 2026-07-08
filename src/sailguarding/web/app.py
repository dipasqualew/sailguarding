"""The framework-free request router behind the dashboard.

Kept as a pure ``(method, path, query) -> Response`` function so the whole surface is testable
without opening a socket: a test constructs an :class:`App` and calls :meth:`App.handle` directly.
The :mod:`.server` module is the only place that touches ``http.server``; everything of substance
lives here and in :mod:`.scenario`.

Every score the API computes runs through a real :class:`Scorer` into a shared
:class:`InMemoryDecisionLog`, so the decision-log panel is the genuine audit trail accumulating as
you move the sliders — not a cosmetic list.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs

from sailguarding.domain import EventRecord
from sailguarding.measurement import InMemoryMetricsSink
from sailguarding.scoring import InMemoryDecisionLog, Scorer
from sailguarding.web import scenario
from sailguarding.web.page import render_page

# The source of the pipeline panel's events. Injected into :class:`App` so tests drive it with a
# fixed list and never touch git; the running server wires in :func:`store_backed_events`.
EventSource = Callable[[], list[EventRecord]]


def store_backed_events() -> list[EventRecord]:
    """Every event the sensor recorded, read from the store the operator config selects.

    This is the honest wire between the sensor and the dashboard: the same
    :class:`~sailguarding.sensor.config.SensorConfig` the hook resolves picks the store (the
    ``sailguarding/events`` branch by default), and we scan it. Kept fail-soft — a missing branch,
    a non-git directory, any storage error yields no events (the panel then shows the demo
    scenario) rather than breaking the page.
    """
    from dataclasses import replace

    from sailguarding.sensor.cli import ENV_PROJECT_DIR
    from sailguarding.sensor.config import (
        SensorConfig,
        build_commit_storage,
        resolve_store_root,
    )
    from sailguarding.sensor.pluginconfig import load_from_env
    from sailguarding.storage.git import SubprocessGitRunner

    try:
        env = os.environ
        repo = Path(env.get(ENV_PROJECT_DIR) or Path.cwd())
        git = SubprocessGitRunner(repo)
        config = SensorConfig.resolve(repo, env, load_from_env(env))
        config = replace(config, store_path=resolve_store_root(git, repo, config.store_path))
        return build_commit_storage(config).scan()
    except Exception:
        return []


# Input ranges the sliders move within; also used to clamp hand-crafted API calls.
FLAKINESS_MAX = 0.05  # 5%
IMPACT_MAX = 100.0  # services affected


@dataclass(frozen=True)
class Response:
    """A rendered HTTP response: status, content type, and body bytes."""

    status: int
    content_type: str
    body: bytes


class App:
    """Holds the demo's decision log and routes requests against it.

    The scoring function is rebuilt per score from the registry-resolved, still-enabled safeguards
    (task 06), so toggling a binding actually changes which ceilings reach the scorer — but every
    score runs through a :class:`Scorer` into the one shared log, so the audit trail is continuous.
    """

    def __init__(self, events_source: EventSource | None = None) -> None:
        self._log = InMemoryDecisionLog()
        # The metrics sink (task 08) — separate from the decision log — accumulates the safeguard's
        # evidence across the session, so ingesting a point moves the derived signal over time.
        self._metrics = scenario.seed_metrics()
        # Where the pipeline panel's events come from. Defaults to *none* so a bare ``App()`` is a
        # hermetic demo (the seed scenario, no I/O); the server injects :func:`store_backed_events`
        # to show the tool calls this repo actually recorded.
        self._events_source: EventSource = events_source or (lambda: [])

    @property
    def log(self) -> InMemoryDecisionLog:
        return self._log

    @property
    def metrics(self) -> InMemoryMetricsSink:
        return self._metrics

    def handle(self, method: str, path: str, query: str = "") -> Response:
        """Route one request. Only ``GET`` is served; everything else is a 405."""
        if method != "GET":
            return _json({"error": f"method {method} not allowed"}, status=405)

        params = parse_qs(query)
        if path == "/":
            return self._index(params)
        if path == "/api/score":
            return _json(self._score(params))
        if path == "/api/ingest":
            return _json(self._ingest(params))
        if path == "/api/pipeline":
            return _json(self._pipeline())
        if path == "/api/decisions":
            return _json({"decisions": self._recent_decisions()})
        return _json({"error": f"not found: {path}"}, status=404)

    def _index(self, params: dict[str, list[str]] | None = None) -> Response:
        # Compute the initial score server-side and embed it, so the first paint is populated even
        # before the page's JS runs (and screenshots / deep links capture a full dashboard).
        params = params or {}
        initial = self._score(params)
        initial["recent"] = self._recent_decisions()  # seed the log panel with real history
        events = self._read_events()
        html = render_page(
            initial_score=initial,
            pipeline=scenario.classified_pipeline(events or None),
            pipeline_source=_pipeline_source(live=bool(events), count=len(events)),
            safeguards=scenario.safeguard_panel(_disabled(params)),
            flakiness_max=FLAKINESS_MAX,
            impact_max=IMPACT_MAX,
            override_remaining=scenario.LEAF_OVERRIDE_REMAINING,
        )
        return Response(200, "text/html; charset=utf-8", html.encode("utf-8"))

    def _pipeline(self) -> dict[str, object]:
        # Read the sensor's recorded events and classify them through the real selector engine.
        # With nothing recorded yet we fall back to the seed scenario so the panel is never blank.
        events = self._read_events()
        rows = scenario.classified_pipeline(events or None)
        return {"events": rows, "live": bool(events), "count": len(events)}

    def _read_events(self) -> list[EventRecord]:
        try:
            return list(self._events_source())
        except Exception:
            return []

    def _ingest(self, params: dict[str, list[str]]) -> dict[str, object]:
        # Append one measurement to the live sink, then re-score: the derived signal (and, for a
        # health point, its ceiling on the float) moves because the evidence history changed.
        kind = "efficacy" if _param_str(params, "kind") == "efficacy" else "health"
        value = _clamp(_param(params, "value", scenario.current_flakiness(self._metrics)), 0.0, 1.0)
        scenario.ingest_measurement(self._metrics, kind=kind, value=value)
        return self._score(params)

    def _score(self, params: dict[str, list[str]]) -> dict[str, object]:
        # The no-flaky-tests signal is derived from ingested evidence (task 08), not a slider.
        flakiness = scenario.current_flakiness(self._metrics)
        services = _clamp(_param(params, "impact", 1.0), 0.0, IMPACT_MAX)
        parent_budget = _clamp(_param(params, "budget", 1.0), 0.0, 1.0)
        override = _flag(params, "override")
        disabled = _disabled(params)

        # The tree resolves the leaf's remaining budget: the parent budget inherited down to
        # write-tests, unless the leaf override wins. That resolved value is what the scorer reads.
        remaining = scenario.resolved_budget(parent_remaining=parent_budget, override=override)
        features = scenario.assemble_features(
            flakiness=flakiness, services_affected=services, remaining_budget=remaining
        )
        scorer = Scorer(scenario.scoring_function(disabled), self._log)
        decision = scorer.score(features)
        breakdown = scenario.ceiling_breakdown(features, disabled)
        binding = next(row for row in breakdown if row["binding"])

        return {
            "score": decision.score,
            "function": {"name": decision.function_name, "version": decision.function_version},
            "binding": binding["label"],
            "ceilings": breakdown,
            "safeguards": scenario.safeguard_panel(disabled),
            "evidence": scenario.evidence_panel(self._metrics),
            "tree": scenario.tree_panel(parent_remaining=parent_budget, override=override),
            "resolved_budget": remaining,
            "features": features.to_dict(),
            "timestamp": decision.timestamp.isoformat().replace("+00:00", "Z"),
            "decisions_logged": len(self._log),
        }

    def _recent_decisions(self, limit: int = 12) -> list[dict[str, object]]:
        decisions = self._log.scan()[-limit:]
        decisions.reverse()  # newest first
        return [
            {
                "score": d.score,
                "function_version": d.function_version,
                "timestamp": d.timestamp.isoformat().replace("+00:00", "Z"),
                "remaining_budget": d.features.remaining_budget,
                "action_id": d.features.action_id,
            }
            for d in decisions
        ]


def _disabled(params: dict[str, list[str]]) -> frozenset[str]:
    """The set of safeguard ids toggled off, from a comma-separated ``disabled`` query param."""
    values = params.get("disabled")
    if not values:
        return frozenset()
    return frozenset(sid for sid in values[0].split(",") if sid)


def _flag(params: dict[str, list[str]], name: str) -> bool:
    """A boolean query flag: true for ``?name=1`` / ``true`` / ``on``, false otherwise."""
    values = params.get(name)
    if not values:
        return False
    return values[0].lower() in {"1", "true", "on", "yes"}


def _param(params: dict[str, list[str]], name: str, default: float) -> float:
    values = params.get(name)
    if not values:
        return default
    try:
        return float(values[0])
    except ValueError:
        return default


def _param_str(params: dict[str, list[str]], name: str, default: str = "") -> str:
    values = params.get(name)
    return values[0] if values else default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _pipeline_source(*, live: bool, count: int) -> str:
    """The panel's provenance line: how many real events, or that it is the demo fallback."""
    if live:
        calls = "call" if count == 1 else "calls"
        return f"Showing {count} recorded tool {calls} from the sensor's event store."
    return "No events recorded yet — showing the demo scenario. Run tools with the plugin enabled."


def _json(payload: object, *, status: int = 200) -> Response:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return Response(status, "application/json; charset=utf-8", body)
