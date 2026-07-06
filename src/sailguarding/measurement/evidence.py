"""One ingested measurement for a safeguard — the platform's *feature substrate*.

An :class:`Evidence` record is a single observation of a safeguard's metric: what was measured,
what value it came out at, **which honest kind of number it is** (health or efficacy), the context
it was measured in, and when. It is the operating team's half of the MLOps division of labour — the
safeguarding team declared *what* each safeguard measures and *which kind* (task 06); this record is
the wired metric source landing that measurement over time.

Two SPEC constraints are load-bearing in this type:

- **The event log is not the metrics.** Evidence is derived, joined to actions *after the fact*, and
  is a time series — a shape git's append-only event log is the wrong home for. So evidence lands in
  its own metrics sink (:mod:`.sink`), never the event-log storage of task 02.
- **Health is not efficacy, ever.** The kind is carried on every record as
  :class:`~sailguarding.safeguards.Measurement` — the *same* enum the safeguard declared — so a
  health proxy can never be read back as the efficacy number that matters. Derivation
  (:mod:`.signal`) keeps the two as separate series and never conflates them.

The record is **versioned, serialisable, and round-trip stable** (``Evidence.from_json(e.to_json())
== e``) and domain-agnostic on purpose: "revert rate" for a code change and "return rate" for a
purchase are the same shape.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sailguarding.domain import Context
from sailguarding.safeguards import Measurement

# Bumped whenever the serialised shape of an Evidence record changes, so a reader can tell which
# schema produced a stored measurement.
EVIDENCE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Evidence:
    """A single measured value for a safeguard, tagged health or efficacy and time-stamped.

    :param safeguard_id: The safeguard this measurement is about (e.g. ``"no-flaky-tests"``).
    :param metric: What was measured (e.g. ``"flakiness"``). Carried for readability; the scoring
        function decides what a value means.
    :param value: The measured value.
    :param measures: :class:`~sailguarding.safeguards.Measurement` — whether this is a ``HEALTH``
        proxy or the lagging ``EFFICACY`` number. The one field the "never conflate" rule turns on.
    :param context: The context the measurement was taken in (``repo``, ``team``, ...).
    :param timestamp: When the measurement was observed. Must be timezone-aware; normalised to UTC
        on construction so equality and the canonical encoding are stable across offsets.
    :param schema_version: The record schema version; defaults to the current one.
    """

    safeguard_id: str
    metric: str
    value: float
    measures: Measurement
    context: Context = field(default_factory=Context)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    schema_version: int = field(default=EVIDENCE_SCHEMA_VERSION)

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("Evidence.timestamp must be timezone-aware")
        # Normalise to UTC so equality and the canonical encoding are stable regardless of the
        # originating offset. object.__setattr__ because the dataclass is frozen.
        object.__setattr__(self, "timestamp", self.timestamp.astimezone(UTC))

    def to_dict(self) -> dict[str, Any]:
        """A JSON-compatible dict; the kind is stored by its stable string value."""
        return {
            "schema_version": self.schema_version,
            "safeguard_id": self.safeguard_id,
            "metric": self.metric,
            "value": self.value,
            "measures": self.measures.value,
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
        return cls(
            safeguard_id=data["safeguard_id"],
            metric=data["metric"],
            value=data["value"],
            measures=Measurement(data["measures"]),
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
