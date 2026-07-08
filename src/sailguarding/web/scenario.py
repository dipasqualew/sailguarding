"""The demo scenario — a small, real :class:`ActivityModel` the editor opens onto.

Nothing here is mock data: the starter model is built purely through the aggregate's own
value-returning transforms (:meth:`ActivityModel.add_activity`, :meth:`add_risk`,
:meth:`add_safeguard`, :meth:`attach_risk`, :meth:`add_mitigation`), so every id is a real slug the
engine minted and every edge is one the engine would accept. The dashboard is a *view* over this
aggregate, and the editor drives the very same transforms live.

The seed is deliberately shaped to show **reuse** — the whole point of keeping risks and safeguards
in shared libraries rather than on the nodes. A single "Human code reviews" safeguard mitigates the
"Break capabilities" risk on *both* "Write software" and "Test software", so its reuse count reads
2; the "Break capabilities" risk itself is faced by two activities. Kept domain-agnostic in spirit:
the same shapes would describe a hardware programme or a purchasing workflow.
"""

from __future__ import annotations

from datetime import timedelta

from sailguarding.model import ActivityModel
from sailguarding.safeguards import Measurement, SafeguardKind


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
