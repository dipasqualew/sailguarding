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
from sailguarding.domain import Action, Context, EventRecord
from sailguarding.measurement import (
    Evidence,
    InMemoryMetricsSink,
    MetricsSink,
    latest_signal,
)
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
from sailguarding.tree import (
    ActionTree,
    BudgetBinding,
    ErrorBudget,
    InMemoryBudgetRegistry,
    resolve_budget,
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


# --- The action tree & error budgets (task 07) -------------------------------------------------
#
# The demo action is a *leaf* in a real tree: shipping the checkout update decomposes into writing
# the tests. A budget declared on the parent inherits down to the leaf; an explicit leaf override
# wins. The *resolved* budget from this chain is exactly the `remaining_budget` the scorer reads —
# so moving the parent budget, or toggling the override, visibly drives the delegation float.
_ROOT_ACTION = "ship-update"
TREE = ActionTree(
    Action(
        id=_ROOT_ACTION,
        label="Ship the checkout update",
        children=(
            Action(id=ACTION_ID, label="Write the tests", parent_id=_ROOT_ACTION),
            Action(id="update-docs", label="Update the docs", parent_id=_ROOT_ACTION),
        ),
    )
)

# The explicit leaf override the demo toggles on: a tighter appetite for write-tests specifically,
# declared *at the leaf*, so it wins over whatever the parent would pass down.
LEAF_OVERRIDE_REMAINING = 0.25
_BUDGET_SELECTOR = Selector(context={"repo": "checkout"})


def budget_registry(*, parent_remaining: float, override: bool) -> InMemoryBudgetRegistry:
    """The budget bindings for the demo: a parent budget, plus an optional leaf override.

    The parent binds to the root action-class in ``repo=checkout``; the leaf override, when on,
    binds to ``write-tests`` directly. Both use the same selector language safeguards bind through.
    """
    registry = InMemoryBudgetRegistry(
        [
            BudgetBinding(
                budget=ErrorBudget("ship-budget", "Ship budget", parent_remaining),
                selector=_BUDGET_SELECTOR,
                action=_ROOT_ACTION,
            )
        ]
    )
    if override:
        registry.register(
            BudgetBinding(
                budget=ErrorBudget("tests-budget", "Tests override", LEAF_OVERRIDE_REMAINING),
                selector=_BUDGET_SELECTOR,
                action=ACTION_ID,
            )
        )
    return registry


def resolved_budget(*, parent_remaining: float, override: bool) -> float:
    """The remaining budget the scorer reads for the demo leaf, resolved through the tree.

    This is the tree driving the float: it is the parent's budget inherited down to ``write-tests``,
    unless the leaf override is on, in which case the leaf's own budget wins.
    """
    registry = budget_registry(parent_remaining=parent_remaining, override=override)
    budget = resolve_budget(TREE, ACTION_ID, CONTEXT, registry)
    return budget.remaining if budget is not None else 1.0


def tree_panel(*, parent_remaining: float, override: bool) -> list[dict[str, object]]:
    """Rows for the action-tree panel: every node with the budget it resolves to and how.

    For each node the panel shows its resolved :class:`ErrorBudget` and whether that budget is
    **declared** at the node or **inherited** from an ancestor — the inheritance rule made visible.
    The demo leaf (``write-tests``) is flagged so the UI can highlight the node the scorer reads.
    """
    registry = budget_registry(parent_remaining=parent_remaining, override=override)
    rows: list[dict[str, object]] = []
    for node in TREE.walk():
        resolved = resolve_budget(TREE, node.id, CONTEXT, registry)
        declared_here = registry.resolve_local(node.id, CONTEXT) is not None
        rows.append(
            {
                "id": node.id,
                "label": node.label,
                "depth": len(TREE.path_to_root(node.id)) - 1,
                "is_leaf": node.is_leaf,
                "is_demo": node.id == ACTION_ID,
                "budget_id": resolved.id if resolved is not None else None,
                "budget_label": resolved.label if resolved is not None else "—",
                "remaining": resolved.remaining if resolved is not None else None,
                "source": "declared" if declared_here else ("inherited" if resolved else "none"),
            }
        )
    return rows


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


# --- Measure: evidence ingestion & the derived signal (task 08) --------------------------------
#
# The no-flaky-tests safeguard's signal is no longer a hand-set slider — it is *derived* from
# ingested evidence. Two series are kept, deliberately never conflated: HEALTH (flakiness, a cheap
# leading proxy) and EFFICACY (catch rate, the lagging truth, back-tested). The safeguard declares
# HEALTH, so the *health* series' latest point is what sets its ceiling on the delegation float;
# the efficacy series is tracked alongside but never feeds the score. Ingesting a health point moves
# the float; ingesting an efficacy point does not — the "never conflate them" rule, made visible.

_HEALTH_METRIC = _FLAKINESS.metric  # "flakiness" — the declared health proxy
_EFFICACY_METRIC = "catch_rate"  # P(catch | actually bad), back-tested — the lagging number
_DEFAULT_FLAKINESS = 0.004  # fallback current signal if no health evidence has been ingested yet


def seed_metrics() -> InMemoryMetricsSink:
    """A metrics sink pre-loaded with a health and an efficacy history for no-flaky-tests.

    Health (flakiness) trends down over the week — the proxy improving; efficacy (catch rate) rises
    more slowly — the lagging truth catching up. Both are the *same* safeguard, kept as two separate
    series in the one sink, so the demo can show them side by side without ever mixing them.
    """
    sink = InMemoryMetricsSink()
    for day, flakiness in enumerate((0.030, 0.022, 0.015, 0.009, 0.006), start=1):
        sink.append(_measurement(Measurement.HEALTH, _HEALTH_METRIC, flakiness, day))
    for day, catch_rate in ((1, 0.72), (3, 0.80), (5, 0.86)):
        sink.append(_measurement(Measurement.EFFICACY, _EFFICACY_METRIC, catch_rate, day))
    return sink


def _measurement(measures: Measurement, metric: str, value: float, day: int) -> Evidence:
    return Evidence(
        safeguard_id=_FLAKINESS.id,
        metric=metric,
        value=value,
        measures=measures,
        context=CONTEXT,
        timestamp=datetime(2026, 7, day, 9, 0, tzinfo=UTC),
    )


def current_flakiness(sink: MetricsSink) -> float:
    """The no-flaky-tests signal the scorer reads: the latest *health* measurement's value.

    This is the whole point of task 08 — the signal that feeds the score is derived from ingested
    evidence, not set by hand. Falls back to a healthy default if nothing has been ingested.
    """
    signal = latest_signal(sink, _FLAKINESS.id, Measurement.HEALTH)
    return float(signal.value) if signal is not None else _DEFAULT_FLAKINESS


def ingest_measurement(
    sink: MetricsSink,
    *,
    kind: str,
    value: float,
    timestamp: datetime | None = None,
) -> Evidence:
    """Append one new measurement for no-flaky-tests to the sink and return it.

    ``kind`` selects the series — ``"efficacy"`` lands in the efficacy series, anything else in
    health — so a caller extends exactly one series and the other is untouched. Timestamps default
    to now, so an ingested point is always the newest and becomes the current signal for its kind.
    """
    measures = Measurement.EFFICACY if kind == "efficacy" else Measurement.HEALTH
    metric = _EFFICACY_METRIC if measures is Measurement.EFFICACY else _HEALTH_METRIC
    evidence = Evidence(
        safeguard_id=_FLAKINESS.id,
        metric=metric,
        value=value,
        measures=measures,
        context=CONTEXT,
        timestamp=timestamp or datetime.now(UTC),
    )
    sink.append(evidence)
    return evidence


def evidence_panel(sink: MetricsSink) -> dict[str, object]:
    """The health and efficacy series for no-flaky-tests, as two clearly-labelled sparklines.

    Each series carries its points (oldest first), its current value, and — for health, the kind
    that governs — the ceiling that value sets on the delegation float. ``drives_ceiling`` marks
    which series the score actually reads, so the UI can show that efficacy is measured but never
    conflated into the health-driven float.
    """
    return {
        "safeguard_id": _FLAKINESS.id,
        "label": _FLAKINESS.label,
        "health": _series_view(sink, Measurement.HEALTH, _HEALTH_METRIC, drives_ceiling=True),
        "efficacy": _series_view(
            sink, Measurement.EFFICACY, _EFFICACY_METRIC, drives_ceiling=False
        ),
    }


def _series_view(
    sink: MetricsSink, measures: Measurement, metric: str, *, drives_ceiling: bool
) -> dict[str, object]:
    points = sink.series(_FLAKINESS.id, measures)
    signal = latest_signal(sink, _FLAKINESS.id, measures)
    current = float(signal.value) if signal is not None else None
    # Only the governing (health) series maps to a ceiling on the float; efficacy is tracked but
    # never scored, so it carries no ceiling — the never-conflate rule, in the data shape.
    ceiling: float | None = None
    if drives_ceiling and current is not None:
        ceiling = _clamp(_FLAKINESS.ceiling(current))
    return {
        "measures": measures.value,
        "metric": metric,
        "points": [
            {"value": e.value, "timestamp": e.timestamp.isoformat().replace("+00:00", "Z")}
            for e in points
        ],
        "current": current,
        "ceiling": ceiling,
        "drives_ceiling": drives_ceiling,
    }


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


def classified_pipeline(events: Iterable[EventRecord] | None = None) -> list[dict[str, object]]:
    """Run the real selector classifier over ``events`` (observe → classify).

    Defaults to the built-in seed events so the demo still renders before anything is recorded; the
    running dashboard passes the *real* events it read from the sensor's store, so the panel shows
    the tool calls this repo actually captured rather than a hardcoded scenario.
    """
    strategy = SelectorClassificationStrategy(_RULES)
    rows: list[dict[str, object]] = []
    for event in _SEED_EVENTS if events is None else events:
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
