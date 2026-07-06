"""The demo scenario — a small, real slice of the engine the dashboard renders.

Nothing here is mock logic: the pipeline runs the actual selector classifier (task 04), governance
runs the actual binding registry (task 06), and the scorer runs the actual ``min``-composition
function (task 05) through a real :class:`Scorer` and :class:`DecisionLog`. The dashboard is a
*view* over the engine, so a demo proves the shipped code, not a re-implementation of it.

The scenario is deliberately the SPEC's worked example: writing tests in the ``checkout`` repo,
governed by two safeguards — **impact** (blast radius) and **no-flaky-tests** (flakiness) — bound to
the ``repo=checkout`` region, with a remaining error budget. Moving the three inputs shows the two
guarantees the scoring contract must honour (impact caps hard, budget pulls the float toward the
human); toggling a binding on/off shows the third thing task 06 proves — that the **registry**
decides which safeguards reach the scorer, so removing one removes its ceiling and the float moves.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from sailguarding.classification import (
    Outcome,
    Selector,
    SelectorClassificationStrategy,
    SelectorRule,
)
from sailguarding.domain import Context, EventRecord
from sailguarding.safeguards import (
    BindingRegistry,
    InMemoryBindingRegistry,
    Measurement,
    Safeguard,
    SafeguardBinding,
    SafeguardKind,
)
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
    """One safeguard in the demo, joining its governance metadata to its scoring and display.

    The :class:`Safeguard` (task 06) is the governance half — id, label, metric, and the
    structural/human-dependent and health/efficacy declarations. The rest is what the demo adds on
    top: how to render its value (``unit``), how its metric maps to a ceiling (``ceiling``, the
    scoring function's business), and a one-line ``rationale`` for the UI.

    :param safeguard: The governed safeguard (task 06).
    :param unit: How to render the value (e.g. ``"%"``, ``" svc"``).
    :param ceiling: Maps the measured value to the highest float this safeguard permits.
    :param rationale: One line explaining the ceiling bands, shown in the UI.
    """

    safeguard: Safeguard
    unit: str
    ceiling: Ceiling
    rationale: str

    @property
    def id(self) -> str:
        return self.safeguard.id

    @property
    def label(self) -> str:
        return self.safeguard.label

    @property
    def metric(self) -> str:
        return self.safeguard.metric


# impact / blast radius: largely human-set and outcome-facing, so it is tagged human-dependent and
# efficacy. (lower is better): <=1 service -> 0.9, <=3 -> 0.5, catastrophic -> 0.
_IMPACT = SafeguardSpec(
    safeguard=Safeguard(
        id="impact",
        label="Blast radius",
        metric="services_affected",
        kind=SafeguardKind.HUMAN_DEPENDENT,
        measures=Measurement.EFFICACY,
    ),
    unit=" svc",
    ceiling=banded_ceiling([(1.0, 0.9), (3.0, 0.5)]),
    rationale="≤1 svc → 0.9, ≤3 → 0.5, catastrophic → 0 (caps hard)",
)
# no flaky tests: run automatically in CI before merge (structural), and flakiness is a leading
# proxy (health). (lower is better): <=1% -> 0.9, <=2% -> 0.5, worse -> 0 (fail toward caution).
_FLAKINESS = SafeguardSpec(
    safeguard=Safeguard(
        id="no-flaky-tests",
        label="No flaky tests",
        metric="flakiness",
        kind=SafeguardKind.STRUCTURAL,
        measures=Measurement.HEALTH,
    ),
    unit="%",
    ceiling=banded_ceiling([(0.01, 0.9), (0.02, 0.5)]),
    rationale="flakiness ≤1% → 0.9, ≤2% → 0.5, worse → 0",
)

SAFEGUARDS: tuple[SafeguardSpec, ...] = (_IMPACT, _FLAKINESS)
_SPEC_BY_ID = {spec.id: spec for spec in SAFEGUARDS}

# The remaining error budget enters as one more ceiling: a nearly-spent budget collapses the
# float toward the human even when every safeguard is holding.
BUDGET_RATIONALE = "remaining budget is its own ceiling — spend it and the float falls"


# --- Governance: which safeguards govern the demo action? (task 06) ----------------------------
#
# Both safeguards bind to the region "repo=checkout, action=write-tests" through the same selector
# language classification uses. The registry — the real engine — resolves the governing set; the
# dashboard's Safeguards panel is a view over exactly this resolution.
_REGISTRY = InMemoryBindingRegistry(
    [
        SafeguardBinding(
            safeguard=_IMPACT.safeguard,
            selector=Selector(context={"repo": "checkout"}),
            action=ACTION_ID,
        ),
        SafeguardBinding(
            safeguard=_FLAKINESS.safeguard,
            selector=Selector(context={"repo": "checkout"}),
            action=ACTION_ID,
        ),
    ]
)


def registry() -> BindingRegistry:
    """The binding registry the dashboard resolves governance through."""
    return _REGISTRY


def governing_specs(disabled: Iterable[str] = ()) -> list[SafeguardSpec]:
    """The demo specs the registry says govern ``(write-tests, checkout)``, minus any disabled.

    Routing through :meth:`BindingRegistry.resolve` is the point of the toggle demo: the *registry*
    decides which safeguards reach the scorer, and disabling one drops it from this list — and so
    from the scoring function built below.
    """
    off = set(disabled)
    specs: list[SafeguardSpec] = []
    for binding in _REGISTRY.resolve(ACTION_ID, CONTEXT):
        sid = binding.safeguard.id
        if sid in off:
            continue
        spec = _SPEC_BY_ID.get(sid)
        if spec is not None:
            specs.append(spec)
    return specs


def safeguard_panel(disabled: Iterable[str] = ()) -> list[dict[str, object]]:
    """Governance rows for the Safeguards panel: every governing safeguard and its enabled state.

    Lists *all* safeguards the registry binds to the action (so a disabled one still shows, greyed),
    each with its structural/human-dependent tag, health/efficacy label, and the selector it bound
    through — proving which safeguards the registry decided reach the scorer.
    """
    off = set(disabled)
    rows: list[dict[str, object]] = []
    for binding in _REGISTRY.resolve(ACTION_ID, CONTEXT):
        sg = binding.safeguard
        rows.append(
            {
                "id": sg.id,
                "label": sg.label,
                "metric": sg.metric,
                "kind": sg.kind.value,
                "measures": sg.measures.value,
                "selector": _selector_label(binding),
                "enabled": sg.id not in off,
            }
        )
    return rows


def _selector_label(binding: SafeguardBinding) -> str:
    """A compact human-readable form of a binding's selector + action, for the panel."""
    parts = [f"{k}={v}" for k, v in sorted(binding.selector.context.items())]
    parts.append(f"action={binding.action}")
    return ", ".join(parts)


def scoring_function(disabled: Iterable[str] = ()) -> MinCompositionScoringFunction:
    """The reference scoring function over exactly the safeguards the registry left enabled.

    Rebuilt per call from :func:`governing_specs`, so a toggled-off safeguard contributes no
    ceiling — the mechanism by which disabling one moves the float in the demo.
    """
    return MinCompositionScoringFunction(
        [SafeguardCeiling(spec.id, spec.ceiling) for spec in governing_specs(disabled)],
        version="1",
    )


def assemble_features(
    *, flakiness: float, services_affected: float, remaining_budget: float
) -> FeatureVector:
    """Assemble the feature vector for the demo action from the three adjustable inputs.

    This is the platform's assembly job (task 05: signals supplied directly for now) made concrete:
    one signal per bound safeguard, plus the context and the remaining budget. Every safeguard's
    signal is carried regardless of the toggle — the scoring function, not the vector, is what a
    disabled safeguard drops out of.
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


def ceiling_breakdown(
    features: FeatureVector, disabled: Iterable[str] = ()
) -> list[dict[str, object]]:
    """Per-input ceilings for the vector, tagged with which one binds (is the minimum).

    Only the safeguards the registry left enabled contribute a row (plus the always-present budget),
    so the breakdown mirrors exactly what the scoring function saw. The smallest ceiling is marked
    ``binding`` — the one that sets the delegation float under ``min``-composition.
    """
    rows: list[dict[str, object]] = []
    for spec in governing_specs(disabled):
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
