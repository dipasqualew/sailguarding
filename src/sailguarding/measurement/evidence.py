"""One ingested attestation for a safeguard — the platform's *feature substrate*.

An :class:`Evidence` record is a single observation of a safeguard's metric: what was measured,
what value it came out at (or **no number at all**, for a structural claim), **which honest kind of
number it is** (health or efficacy), the operating team's **reasoning**, the context it was measured
in, when, and **how long it stays valid**. It is the operating team's half of the MLOps division of
labour — the safeguarding team declared *what* each safeguard measures, *which kind*, and *how
often* it must be re-evidenced (task 06, task 09); this record is the wired metric source landing
that attestation over time.

Three SPEC constraints are load-bearing in this type:

- **The event log is not the metrics.** Evidence is derived, joined to activities *after the
  fact*, and is a time series — a shape git's append-only event log is the wrong home for. So
  evidence lands in
  its own metrics sink (:mod:`.sink`), never the event-log storage of task 02.
- **Health is not efficacy, ever.** The kind is carried on every record as
  :class:`~sailguarding.safeguards.Measurement` — the *same* enum the safeguard declared — so a
  health proxy can never be read back as the efficacy number that matters. Derivation
  (:mod:`.signal`) keeps the two as separate series and never conflates them.
- **Delegation is a subscription.** A record carries a **validity window** (``valid_for``): fresh
  evidence buys allowance for exactly that window, and once it lapses the record is *stale* and
  contributes no signal — the safeguard fails toward caution. ``valid_for is None`` is evidence that
  never expires. The window is derived from the safeguard's cadence at attestation time; deriving
  ``expires_at`` from ``timestamp + valid_for`` keeps the record self-describing without storing a
  redundant field.

The record is **versioned, serialisable, and round-trip stable** (``Evidence.from_json(e.to_json())
== e``) and domain-agnostic on purpose: "return rate ≤ 2%" for a purchase and "ephemeral envs
verified" for a deploy are the same shape with the same shelf life.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sailguarding.domain import Context
from sailguarding.safeguards import Measurement

# Bumped whenever the serialised shape of an Evidence record changes, so a reader can tell which
# schema produced a stored measurement. v2 added the attestation fields — reasoning, the validity
# window, and a nullable value for a non-metric structural claim (task 09).
EVIDENCE_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class Evidence:
    """A single attestation for a safeguard: a value (or none), its reasoning, and its shelf life.

    :param safeguard_id: The safeguard this attestation is about (e.g. ``"no-flaky-tests"``).
    :param metric: What was measured (e.g. ``"flakiness"``). Carried for readability; the scoring
        function decides what a value means.
    :param value: The measured value, or ``None`` for a **structural attestation** — a claim that
        the control holds with no number attached (e.g. "ephemeral envs verified").
    :param measures: :class:`~sailguarding.safeguards.Measurement` — whether this is a ``HEALTH``
        proxy or the lagging ``EFFICACY`` number. The one field the "never conflate" rule turns on.
    :param reasoning: Free text — how the operating team knows the control holds. Carried into the
        audit trail so an attestation is never a bare number.
    :param valid_for: How long this attestation stays fresh, derived from the safeguard's cadence at
        attestation time. ``None`` (the default) is evidence that never expires; a
        :class:`~datetime.timedelta` gives it a shelf life, after which it is stale.
    :param context: The context the measurement was taken in (``repo``, ``team``, ...).
    :param timestamp: When the measurement was observed. Must be timezone-aware; normalised to UTC
        on construction so equality and the canonical encoding are stable across offsets.
    :param schema_version: The record schema version; defaults to the current one.
    """

    safeguard_id: str
    metric: str
    value: float | None
    measures: Measurement
    reasoning: str = ""
    valid_for: timedelta | None = None
    context: Context = field(default_factory=Context)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    schema_version: int = field(default=EVIDENCE_SCHEMA_VERSION)

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("Evidence.timestamp must be timezone-aware")
        if self.valid_for is not None and self.valid_for <= timedelta(0):
            raise ValueError(
                "Evidence.valid_for must be a positive window, or None to never expire"
            )
        # Normalise to UTC so equality and the canonical encoding are stable regardless of the
        # originating offset. object.__setattr__ because the dataclass is frozen.
        object.__setattr__(self, "timestamp", self.timestamp.astimezone(UTC))

    @property
    def expires_at(self) -> datetime | None:
        """The instant this attestation goes stale, or ``None`` if it never expires.

        Derived from ``timestamp + valid_for`` rather than stored, so the window and its expiry can
        never disagree. The timestamp is already UTC, so the expiry is too.
        """
        if self.valid_for is None:
            return None
        return self.timestamp + self.valid_for

    def is_fresh(self, now: datetime) -> bool:
        """Whether this attestation still holds at ``now`` — a **cliff** at expiry, not a ramp.

        Evidence with no window is always fresh; otherwise it is fresh strictly *before* its
        ``expires_at`` and stale from that instant on. ``now`` is injected so freshness is a pure
        function of the record and the clock the caller supplies (never wall time reached for here).
        """
        expires = self.expires_at
        return expires is None or now < expires

    def to_dict(self) -> dict[str, Any]:
        """A JSON-compatible dict; the kind is stored by its stable string value.

        The validity window is stored as ``valid_for_seconds`` (a plain number, or ``null`` for
        never-expiring evidence); ``expires_at`` is *not* stored — it is derived on read so the two
        can never drift apart.
        """
        return {
            "schema_version": self.schema_version,
            "safeguard_id": self.safeguard_id,
            "metric": self.metric,
            "value": self.value,
            "measures": self.measures.value,
            "reasoning": self.reasoning,
            "valid_for_seconds": (
                self.valid_for.total_seconds() if self.valid_for is not None else None
            ),
            "context": dict(self.context),
            "timestamp": self.timestamp.isoformat().replace("+00:00", "Z"),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Evidence:
        """Rebuild an evidence record from :meth:`to_dict`, rejecting an unknown schema version."""
        version = data.get("schema_version", EVIDENCE_SCHEMA_VERSION)
        if version != EVIDENCE_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported Evidence schema_version {version!r}; "
                f"this build reads version {EVIDENCE_SCHEMA_VERSION}"
            )
        valid_for_seconds = data.get("valid_for_seconds")
        return cls(
            safeguard_id=data["safeguard_id"],
            metric=data["metric"],
            value=data["value"],
            measures=Measurement(data["measures"]),
            reasoning=data.get("reasoning", ""),
            valid_for=(
                timedelta(seconds=valid_for_seconds) if valid_for_seconds is not None else None
            ),
            context=Context(data.get("context", {})),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            schema_version=version,
        )

    def to_json(self) -> str:
        """Serialise to a canonical, single-line JSON string (sorted keys, tight separators)."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> Evidence:
        """Parse an evidence record from a JSON string produced by :meth:`to_json`."""
        return cls.from_dict(json.loads(text))
