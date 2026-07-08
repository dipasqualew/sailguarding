"""The feature vector — the typed input the platform assembles for one score.

This is the *substrate* half of the SPEC's division of labour: the platform collects the
measured signals for an ``(activity, context)`` — one per bound safeguard — plus the context it
ran in and the remaining error budget, and hands that whole vector to the team's scoring
function. The platform never interprets a signal; it only assembles, serialises, and logs it.

The vector is **versioned and serialisable on purpose**: it is written verbatim into the
decision log with every score (:mod:`.decision`), so a round-trip must be byte-stable and
lossless — "why was this delegated at 0.9?" is answered by replaying the exact inputs months
later. Round-trip identity holds: ``FeatureVector.from_json(v.to_json()) == v``.

For this task signals are **supplied directly** — there is no live ingestion yet. The schema is
what matters; wiring calibrated signals into it is a later task.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from sailguarding.domain import Context

# Bumped whenever the shape of a serialised FeatureVector changes. Logged with every decision
# so a reader can tell which schema produced a stored vector. v2 renamed ``action_id`` to
# ``activity_id`` (the Action → Activity rename).
FEATURE_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class SafeguardSignal:
    """One measured signal from a bound safeguard.

    The platform carries the number; the team's function decides what it means. ``metric`` names
    *what* was measured (``"flakiness"``, ``"coverage"``, ``"impact"``) and ``value`` is the
    measurement. One signal per bound safeguard in v1 — a safeguard reports the single metric its
    class scores against.

    :param safeguard_id: Stable id of the safeguard the signal came from (e.g. ``"no-flaky"``).
    :param metric: Name of the measured metric, for readability in the decision log.
    :param value: The measured value. Semantics (higher-is-better vs. -worse) live in the scoring
        function, not here.
    """

    safeguard_id: str
    metric: str
    value: float

    def to_dict(self) -> dict[str, Any]:
        return {"safeguard_id": self.safeguard_id, "metric": self.metric, "value": self.value}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SafeguardSignal:
        return cls(
            safeguard_id=data["safeguard_id"],
            metric=data["metric"],
            value=data["value"],
        )


@dataclass(frozen=True)
class FeatureVector:
    """The complete input to one score: signals, context, and remaining budget.

    :param signals: One :class:`SafeguardSignal` per bound safeguard, in a stable order.
    :param context: The context dimensions the activity ran in (``repo``, ``team``, ...).
    :param remaining_budget: The fraction of the error budget still unspent, ``0.0`` (exhausted)
        to ``1.0`` (full). The platform does not enforce this range — a team's function reads it —
        but the reference example treats it as a ceiling that pulls the float toward the human.
    :param activity_id: The activity being scored, if known; ``None`` when scoring a bare vector.
    :param schema_version: The vector schema version; defaults to the current one.
    """

    signals: tuple[SafeguardSignal, ...] = ()
    context: Context = field(default_factory=Context)
    remaining_budget: float = 1.0
    activity_id: str | None = None
    schema_version: int = FEATURE_SCHEMA_VERSION

    def signal(self, safeguard_id: str) -> SafeguardSignal | None:
        """The signal from ``safeguard_id``, or ``None`` if that safeguard reported none."""
        for signal in self.signals:
            if signal.safeguard_id == safeguard_id:
                return signal
        return None

    def to_dict(self) -> dict[str, Any]:
        """A plain JSON-compatible dict. Written verbatim into the decision log."""
        return {
            "schema_version": self.schema_version,
            "signals": [signal.to_dict() for signal in self.signals],
            "context": dict(self.context),
            "remaining_budget": self.remaining_budget,
            "activity_id": self.activity_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FeatureVector:
        """Rebuild a vector from :meth:`to_dict` output, rejecting an unknown schema version."""
        version = data.get("schema_version", FEATURE_SCHEMA_VERSION)
        if version != FEATURE_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported FeatureVector schema_version {version!r}; "
                f"this build reads version {FEATURE_SCHEMA_VERSION}"
            )
        return cls(
            signals=tuple(SafeguardSignal.from_dict(s) for s in data.get("signals", ())),
            context=Context(data.get("context", {})),
            remaining_budget=data.get("remaining_budget", 1.0),
            activity_id=data.get("activity_id"),
            schema_version=version,
        )

    def to_json(self) -> str:
        """Serialise to a canonical, single-line JSON string (sorted keys, tight separators)."""
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, text: str) -> FeatureVector:
        """Parse a vector from a JSON string produced by :meth:`to_json`."""
        return cls.from_dict(json.loads(text))


def feature_vector(
    signals: Iterable[SafeguardSignal] = (),
    *,
    context: Context | Mapping[str, Any] | None = None,
    remaining_budget: float = 1.0,
    activity_id: str | None = None,
) -> FeatureVector:
    """Assemble a :class:`FeatureVector`, coercing ``context`` from a plain mapping if needed.

    A small convenience for callers (and tests) that hold context as a dict rather than a
    :class:`Context`; the platform's real assembly path would pass a resolved ``Context`` directly.
    """
    resolved = context if isinstance(context, Context) else Context(context or {})
    return FeatureVector(
        signals=tuple(signals),
        context=resolved,
        remaining_budget=remaining_budget,
        activity_id=activity_id,
    )
