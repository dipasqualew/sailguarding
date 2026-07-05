"""The demo scenario — a small, real slice of the engine the dashboard renders.

Nothing here is mock logic: the pipeline runs the actual selector classifier (task 04) over seed
events, and the scorer runs the actual ``min``-composition function (task 05) through a real
:class:`Scorer` and :class:`DecisionLog`. The dashboard is a *view* over the engine, so a demo
proves the shipped code, not a re-implementation of it.

The scenario is deliberately the SPEC's worked example: writing tests in the ``checkout`` repo,
governed by two safeguards — **impact** (blast radius) and **no-flaky-tests** (flakiness) — with a
remaining error budget. Moving the three inputs shows the two guarantees the scoring contract must
honour: impact caps hard, and budget pulls the float toward the human.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from sailguarding.classification import (
    Outcome,
    Selector,
    SelectorClassificationStrategy,
    SelectorRule,
)
from sailguarding.domain import Context, EventRecord
from sailguarding.scoring import (
    Ceiling,
    FeatureVector,
    MinCompositionScoringFunction,
    SafeguardCeiling,
    SafeguardSignal,
    banded_ceiling,
)

ACTION_ID = "write-tests"
CONTEXT = Context(repo="checkout", team="core", environment="ci")


@dataclass(frozen=True)
class SafeguardSpec:
    """One safeguard in the demo: how to read its input and how its metric maps to a ceiling.

    :param id: The safeguard id used in the feature vector.
    :param label: Human-readable name for the dashboard.
    :param metric: The metric name recorded on the signal.
    :param unit: How to render the value (e.g. ``"%"``, ``" svc"``).
    :param ceiling: Maps the measured value to the highest float this safeguard permits.
    :param rationale: One line explaining the ceiling bands, shown in the UI.
    """

    id: str
    label: str
    metric: str
    unit: str
    ceiling: Ceiling
    rationale: str


# flakiness (lower is better): <=1% -> 0.9, <=2% -> 0.5, worse -> 0 (fail toward caution).
_FLAKINESS = SafeguardSpec(
    id="no-flaky-tests",
    label="No flaky tests",
    metric="flakiness",
    unit="%",
    ceiling=banded_ceiling([(0.01, 0.9), (0.02, 0.5)]),
    rationale="flakiness ≤1% → 0.9, ≤2% → 0.5, worse → 0",
)
# impact / blast radius (lower is better): <=1 service -> 0.9, <=3 -> 0.5, catastrophic -> 0.
_IMPACT = SafeguardSpec(
    id="impact",
    label="Blast radius",
    metric="services_affected",
    unit=" svc",
    ceiling=banded_ceiling([(1.0, 0.9), (3.0, 0.5)]),
    rationale="≤1 svc → 0.9, ≤3 → 0.5, catastrophic → 0 (caps hard)",
)

SAFEGUARDS: tuple[SafeguardSpec, ...] = (_IMPACT, _FLAKINESS)

# The remaining error budget enters as one more ceiling: a nearly-spent budget collapses the
# float toward the human even when every safeguard is holding.
BUDGET_RATIONALE = "remaining budget is its own ceiling — spend it and the float falls"

_FUNCTION = MinCompositionScoringFunction(
    [SafeguardCeiling(spec.id, spec.ceiling) for spec in SAFEGUARDS],
    version="1",
)


def scoring_function() -> MinCompositionScoringFunction:
    """The reference scoring function the dashboard executes."""
    return _FUNCTION


def assemble_features(
    *, flakiness: float, services_affected: float, remaining_budget: float
) -> FeatureVector:
    """Assemble the feature vector for the demo action from the three adjustable inputs.

    This is the platform's assembly job (task 05: signals supplied directly for now) made concrete:
    one signal per bound safeguard, plus the context and the remaining budget.
    """
    return FeatureVector(
        signals=(
            SafeguardSignal(_IMPACT.id, _IMPACT.metric, services_affected),
            SafeguardSignal(_FLAKINESS.id, _FLAKINESS.metric, flakiness),
        ),
        context=CONTEXT,
        remaining_budget=remaining_budget,
        action_id=ACTION_ID,
    )


def ceiling_breakdown(features: FeatureVector) -> list[dict[str, object]]:
    """Per-input ceilings for the vector, tagged with which one binds (is the minimum).

    Recomputes each safeguard's ceiling and the budget ceiling for display, then marks the smallest
    as ``binding`` — the one that sets the delegation float under ``min``-composition.
    """
    rows: list[dict[str, object]] = []
    for spec in SAFEGUARDS:
        signal = features.signal(spec.id)
        value = float(signal.value) if signal is not None else 0.0
        rows.append(
            {
                "id": spec.id,
                "label": spec.label,
                "value": value,
                "unit": spec.unit,
                "ceiling": _clamp(spec.ceiling(value)),
                "rationale": spec.rationale,
            }
        )
    rows.append(
        {
            "id": "remaining-budget",
            "label": "Remaining budget",
            "value": features.remaining_budget,
            "unit": "%",
            "ceiling": _clamp(features.remaining_budget),
            "rationale": BUDGET_RATIONALE,
        }
    )

    binding = min(rows, key=lambda row: row["ceiling"])  # type: ignore[arg-type,return-value]
    for row in rows:
        row["binding"] = row is binding
    return rows


# --- The observe → classify pipeline, shown as supporting context above the scorer. ------------

_RULES = (
    SelectorRule(
        selector=Selector(tool="Edit", path="**/*.test.ts", context={"repo": "checkout"}),
        action_id="write-tests",
    ),
    SelectorRule(
        selector=Selector(tool="Edit", path="**/*.ts", context={"repo": "checkout"}),
        action_id="write-code",
        priority=-1,
    ),
    SelectorRule(
        selector=Selector(tool="Bash", command="*deploy*"),
        action_id="deploy",
    ),
)


def _event(tool: str, tool_input: Mapping[str, object], *, minute: int) -> EventRecord:
    return EventRecord(
        session_id="demo-session",
        harness_id="claude-code",
        tool_name=tool,
        tool_input=dict(tool_input),
        context=CONTEXT,
        timestamp=datetime(2026, 7, 5, 12, minute, tzinfo=UTC),
    )


_SEED_EVENTS = (
    _event("Edit", {"file_path": "src/cart.test.ts"}, minute=1),
    _event("Edit", {"file_path": "src/cart.ts"}, minute=2),
    _event("Bash", {"command": "npm run deploy:staging"}, minute=3),
    _event("Bash", {"command": "npm test"}, minute=4),
)


def classified_pipeline() -> list[dict[str, object]]:
    """Run the real selector classifier over the seed events (observe → classify)."""
    strategy = SelectorClassificationStrategy(_RULES)
    rows: list[dict[str, object]] = []
    for event in _SEED_EVENTS:
        result = strategy.classify(event)
        rows.append(
            {
                "tool": event.tool_name,
                "input": _describe_input(event),
                "outcome": result.outcome.value,
                "action_id": result.action_id,
                "resolved": result.outcome is Outcome.MATCHED,
            }
        )
    return rows


def _describe_input(event: EventRecord) -> str:
    for key in ("file_path", "command"):
        value = event.tool_input.get(key)
        if isinstance(value, str):
            return value
    return ""


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
