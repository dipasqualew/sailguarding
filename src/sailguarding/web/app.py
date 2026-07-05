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
from dataclasses import dataclass
from urllib.parse import parse_qs

from sailguarding.scoring import InMemoryDecisionLog, Scorer
from sailguarding.web import scenario
from sailguarding.web.page import render_page

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
    """Holds the demo's decision log + scorer and routes requests against them."""

    def __init__(self) -> None:
        self._log = InMemoryDecisionLog()
        self._scorer = Scorer(scenario.scoring_function(), self._log)

    @property
    def log(self) -> InMemoryDecisionLog:
        return self._log

    def handle(self, method: str, path: str, query: str = "") -> Response:
        """Route one request. Only ``GET`` is served; everything else is a 405."""
        if method != "GET":
            return _json({"error": f"method {method} not allowed"}, status=405)

        params = parse_qs(query)
        if path == "/":
            return self._index(params)
        if path == "/api/score":
            return _json(self._score(params))
        if path == "/api/pipeline":
            return _json({"events": scenario.classified_pipeline()})
        if path == "/api/decisions":
            return _json({"decisions": self._recent_decisions()})
        return _json({"error": f"not found: {path}"}, status=404)

    def _index(self, params: dict[str, list[str]] | None = None) -> Response:
        # Compute the initial score server-side and embed it, so the first paint is populated even
        # before the page's JS runs (and screenshots / deep links capture a full dashboard).
        initial = self._score(params or {})
        initial["recent"] = self._recent_decisions()  # seed the log panel with real history
        html = render_page(
            initial_score=initial,
            pipeline=scenario.classified_pipeline(),
            safeguards=[
                {"id": s.id, "label": s.label, "unit": s.unit, "rationale": s.rationale}
                for s in scenario.SAFEGUARDS
            ],
            flakiness_max=FLAKINESS_MAX,
            impact_max=IMPACT_MAX,
        )
        return Response(200, "text/html; charset=utf-8", html.encode("utf-8"))

    def _score(self, params: dict[str, list[str]]) -> dict[str, object]:
        flakiness = _clamp(_param(params, "flakiness", 0.004), 0.0, FLAKINESS_MAX)
        services = _clamp(_param(params, "impact", 1.0), 0.0, IMPACT_MAX)
        budget = _clamp(_param(params, "budget", 1.0), 0.0, 1.0)

        features = scenario.assemble_features(
            flakiness=flakiness, services_affected=services, remaining_budget=budget
        )
        decision = self._scorer.score(features)
        breakdown = scenario.ceiling_breakdown(features)
        binding = next(row for row in breakdown if row["binding"])

        return {
            "score": decision.score,
            "function": {"name": decision.function_name, "version": decision.function_version},
            "binding": binding["label"],
            "ceilings": breakdown,
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


def _param(params: dict[str, list[str]], name: str, default: float) -> float:
    values = params.get(name)
    if not values:
        return default
    try:
        return float(values[0])
    except ValueError:
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _json(payload: object, *, status: int = 200) -> Response:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return Response(status, "application/json; charset=utf-8", body)
