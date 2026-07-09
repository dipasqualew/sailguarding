"""The demo scenario — a small, real :class:`Workspace` of :class:`ActivityModel`\\ s to open onto.

Nothing here is mock data: every model is built purely through the aggregates' own value-returning
transforms (:meth:`ActivityModel.add_activity`, :meth:`add_risk`, :meth:`add_safeguard`,
:meth:`attach_risk`, :meth:`add_mitigation`, :meth:`set_applies_when`), so every id is a real slug
the engine minted and every edge is one the engine would accept. The dashboard is a *view* over
these aggregates, and the editor drives the very same transforms live.

:func:`seed_workspace` returns **three** models that show why a workspace exists:

- **Product Software Engineering** (:func:`seed_model`) — scoped to ``repo ∈ {checkout, billing}``,
  and shaped to show *reuse*: one "Human code reviews" safeguard mitigates "Break capabilities" on
  both "Write software" and "Test software".
- **Platform Software Engineering** — scoped to ``repo ∈ {infra, platform}``. It shares the
  "Ephemeral environments" safeguard *shape* with Product, so importing one of its activities into
  Product **dedupes** the safeguard rather than duplicating it — the payoff of partial overlap.
- **Sales** — scoped to ``team = sales``. Deliberately disjoint (proposals, not code) to show a
  model that does not overlap the others at all.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from sailguarding.model import ActivityModel, ContextScope, Workspace
from sailguarding.safeguards import Measurement, SafeguardKind


def seed_workspace() -> Workspace:
    """A starter :class:`Workspace` of three models — Product, Platform, and Sales.

    The models are ordered Product → Platform → Sales, with Product active, so the editor opens onto
    the richest model while the switcher shows there are others to navigate to.
    """
    product = replace(
        seed_model(), id="product-software-engineering", name="Product Software Engineering"
    )
    product = product.set_applies_when(
        ContextScope.empty().set_dimension("repo", ("checkout", "billing"))
    )
    return Workspace.of(product, seed_platform_model(), seed_sales_model())


def seed_model() -> ActivityModel:
    """A small, compelling starter model that exercises risk and safeguard reuse.

    Structure: a top-level "Develop new capabilities" activity decomposing into "Write software" and
    "Test software". Three reusable risks and two reusable safeguards, wired so the shared "Human
    code reviews" safeguard covers the same risk on two activities — the reuse story the library
    shape exists to tell.
    """
    model = ActivityModel.empty()

    model, develop = model.add_activity(None, "Develop new capabilities")
    model, write = model.add_activity(develop, "Write software")
    model, test = model.add_activity(develop, "Test software")

    model, break_caps = model.add_risk(
        "Break capabilities", "A change regresses behaviour that used to work."
    )
    model, data_loss = model.add_risk(
        "Data loss", "Irreversible loss or corruption of production data."
    )
    model, opportunity = model.add_risk(
        "Opportunity cost", "Effort spent here is effort not spent on higher-value work."
    )

    # The shared safeguard: one control, reused across activities. Human-dependent (a person must do
    # the review) and efficacy (it is the lagging number that actually catches regressions).
    model, reviews = model.add_safeguard(
        "Human code reviews",
        SafeguardKind.HUMAN_DEPENDENT,
        Measurement.EFFICACY,
        metric="reviews_completed",
        cadence=timedelta(days=7),
    )
    # A structural safeguard measured by a cheap leading proxy (health).
    model, ephemeral = model.add_safeguard(
        "Ephemeral environments",
        SafeguardKind.STRUCTURAL,
        Measurement.HEALTH,
        metric="env_isolation",
    )

    # Which risks each activity faces.
    model = model.attach_risk(develop, opportunity)
    model = model.attach_risk(write, break_caps)
    model = model.attach_risk(write, data_loss)
    model = model.attach_risk(test, break_caps)

    # The reuse story: "Human code reviews" mitigates "Break capabilities" on BOTH activities, so
    # its reuse count reads 2. "Ephemeral environments" guards data loss on the writing activity.
    model = model.add_mitigation(write, break_caps, reviews)
    model = model.add_mitigation(test, break_caps, reviews)
    model = model.add_mitigation(write, data_loss, ephemeral)

    return model


def seed_platform_model() -> ActivityModel:
    """The "Platform Software Engineering" model — scoped to the infra repos.

    It deliberately re-uses the "Ephemeral environments" and "Data loss" slugs that Product also
    has, so importing "Provision infrastructure" into Product dedupes them rather than duplicating —
    the partial-overlap payoff the workspace exists to show.
    """
    model = ActivityModel.empty(
        model_id="platform-software-engineering", name="Platform Software Engineering"
    )
    model = model.set_applies_when(
        ContextScope.empty().set_dimension("repo", ("infra", "platform"))
    )

    model, operate = model.add_activity(None, "Operate the platform")
    model, provision = model.add_activity(operate, "Provision infrastructure")
    model, migrate = model.add_activity(operate, "Run database migrations")

    model, data_loss = model.add_risk(
        "Data loss", "Irreversible loss or corruption of production data."
    )
    model, outage = model.add_risk("Outage", "A change takes a production service offline.")

    model, ephemeral = model.add_safeguard(
        "Ephemeral environments",
        SafeguardKind.STRUCTURAL,
        Measurement.HEALTH,
        metric="env_isolation",
    )
    model, canary = model.add_safeguard(
        "Canary rollout",
        SafeguardKind.STRUCTURAL,
        Measurement.EFFICACY,
        metric="canary_catch_rate",
        cadence=timedelta(days=1),
    )

    model = model.attach_risk(provision, data_loss)
    model = model.attach_risk(provision, outage)
    model = model.attach_risk(migrate, data_loss)

    model = model.add_mitigation(provision, data_loss, ephemeral)
    model = model.add_mitigation(provision, outage, canary)
    model = model.add_mitigation(migrate, data_loss, ephemeral)

    return model


def seed_sales_model() -> ActivityModel:
    """The "Sales" model — scoped to ``team = sales``, disjoint from the code models.

    Its point is to show a model that does not overlap the engineering ones at all: different
    activities, risks, and safeguards, a different context dimension entirely.
    """
    model = ActivityModel.empty(model_id="sales", name="Sales")
    model = model.set_applies_when(ContextScope.empty().set_dimension("team", ("sales",)))

    model, close = model.add_activity(None, "Close new business")
    model, _qualify = model.add_activity(close, "Qualify the lead")
    model, propose = model.add_activity(close, "Send the proposal")

    model, overpromise = model.add_risk(
        "Overpromise", "Committing to scope or dates the team cannot deliver."
    )
    model, discount = model.add_risk(
        "Unapproved discount", "Pricing below the floor the business set."
    )

    model, signoff = model.add_safeguard(
        "Manager sign-off",
        SafeguardKind.HUMAN_DEPENDENT,
        Measurement.EFFICACY,
        metric="deals_reviewed",
        cadence=timedelta(days=1),
    )
    model, pricing_guard = model.add_safeguard(
        "Pricing guardrails",
        SafeguardKind.STRUCTURAL,
        Measurement.HEALTH,
        metric="quotes_within_floor",
    )

    model = model.attach_risk(propose, overpromise)
    model = model.attach_risk(propose, discount)

    model = model.add_mitigation(propose, overpromise, signoff)
    model = model.add_mitigation(propose, discount, pricing_guard)

    return model
