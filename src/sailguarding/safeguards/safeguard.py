"""The governed safeguard — the SPEC's *separation of powers* made into a type.

A safeguard has two authors, and this type carries only what the **safeguarding team** owns: the
*class* (what must be true for an action to be delegable) and the declarations that decide how much
a signal is allowed to move the float. The **operating team**'s half — how *this* context actually
computes and ingests the metric — is not here; that is measurement (task 08). Nor is the *scoring*
(how failing the metric maps to a ceiling): that lives in the team's scoring function (task 05), a
competitive asset the platform never owns. A :class:`Safeguard` is the governance metadata the
platform *does* hold and serve.

Two declarations the platform must carry honestly, because both change how far a signal can push
the delegation float:

- **Structural vs. human-dependent** (:class:`SafeguardKind`). A spending cap the model cannot
  exceed is enforced by construction; "I'll review the shortlist" is a promise. Human-dependent
  safeguards move the score less than they appear to, and the platform must be able to say which is
  which — SPEC design principle 3, *structural beats human-dependent*.
- **Health vs. efficacy** (:class:`Measurement`). Health is cheap, leading, a proxy (flakiness,
  coverage delta); efficacy is the lagging number that matters (``P(catch | bad)``). Selling health
  as efficacy is the trap the SPEC names; the type forces each safeguard to *declare* which, so the
  two are never conflated — SPEC design principle 2, *measure honestly*.

The type is **versioned, serialisable, and round-trip stable** (``Safeguard.from_json(s.to_json())
== s``) because a binding — and, downstream, a logged decision — records it verbatim. It is
domain-agnostic on purpose: the same shape governs a code edit and a sofa purchase.
"""

from __future__ import annotations

import enum
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

# Bumped whenever the serialised shape of a Safeguard changes, so a reader can tell which schema
# produced a stored record.
SAFEGUARD_SCHEMA_VERSION = 1


class SafeguardKind(enum.Enum):
    """Whether a safeguard is enforced by construction or leans on a human.

    ``STRUCTURAL`` safeguards cannot be bypassed by the agent (a hard spending cap, a required
    status check); ``HUMAN_DEPENDENT`` ones rely on a person doing the thing they said they would
    (a manual review). The distinction is load-bearing: a team's scoring function should let a
    structural safeguard lift the float further than a human-dependent one, and it can only do that
    if the platform records which is which.
    """

    STRUCTURAL = "structural"
    HUMAN_DEPENDENT = "human_dependent"


class Measurement(enum.Enum):
    """Which honest kind of number a safeguard's metric is — a proxy, or the thing itself.

    ``HEALTH`` is cheap, continuous, and leading — a proxy that can rise or fall well before an
    outcome (flakiness, coverage delta, CI latency). ``EFFICACY`` is expensive and lagging — the
    number that actually matters, back-tested against outcomes (``P(catch a bad change | change was
    bad)``). A safeguard declares one; the platform never lets a health metric be sold as efficacy.
    """

    HEALTH = "health"
    EFFICACY = "efficacy"


@dataclass(frozen=True)
class Safeguard:
    """A control the safeguarding team requires for an action to be delegable.

    :param id: Stable identifier, referenced by a signal and by every binding (e.g.
        ``"no-flaky-tests"``).
    :param label: Human-readable name for dashboards and audit trails.
    :param metric: The single metric this safeguard's class scores against (e.g. ``"flakiness"``).
        The platform carries the name; the scoring function decides what a value means.
    :param kind: :class:`SafeguardKind` — structural or human-dependent.
    :param measures: :class:`Measurement` — whether ``metric`` is health or efficacy.
    :param schema_version: The record schema version; defaults to the current one.
    """

    id: str
    label: str
    metric: str
    kind: SafeguardKind
    measures: Measurement
    schema_version: int = field(default=SAFEGUARD_SCHEMA_VERSION)

    def to_dict(self) -> dict[str, Any]:
        """A JSON-compatible dict; enums are stored by their stable string values."""
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "label": self.label,
            "metric": self.metric,
            "kind": self.kind.value,
            "measures": self.measures.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Safeguard:
        """Rebuild a safeguard from :meth:`to_dict` output, rejecting an unknown schema version."""
        version = data.get("schema_version", SAFEGUARD_SCHEMA_VERSION)
        if version != SAFEGUARD_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported Safeguard schema_version {version!r}; "
                f"this build reads version {SAFEGUARD_SCHEMA_VERSION}"
            )
        return cls(
            id=data["id"],
            label=data["label"],
            metric=data["metric"],
            kind=SafeguardKind(data["kind"]),
            measures=Measurement(data["measures"]),
            schema_version=version,
        )

    def to_json(self) -> str:
        """Serialise to a canonical, single-line JSON string (sorted keys, tight separators)."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> Safeguard:
        """Parse a safeguard from a JSON string produced by :meth:`to_json`."""
        return cls.from_dict(json.loads(text))
