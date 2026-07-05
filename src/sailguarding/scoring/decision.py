"""The decision log — model risk management pointed at the scorer.

Every score is a decision made by a model, so it inherits SR 11-7: unversioned, unlogged
arbitrary code is not acceptable; *logged* arbitrary code is. A :class:`Decision` records the four
things that make a score auditable — the exact **inputs** (the feature vector), the **function
identity + version** that produced it, the **output** float, and a **timestamp** — so "why was
this delegated at 0.9?" is answerable months later by replaying the entry.

Reading a decision back reproduces its inputs exactly: round-trip identity holds
(``Decision.from_json(d.to_json()) == d``), and the embedded :class:`FeatureVector` round-trips
losslessly, so the stored decision *is* the reproducible record, not a lossy summary.

The log itself is a pluggable sink mirroring the storage seam: :class:`DecisionLog` is the minimal
contract and :class:`InMemoryDecisionLog` is the injectable default for tests. A durable,
git-native sink can implement the same shape later.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from sailguarding.scoring.features import FeatureVector

# Bumped whenever the on-disk shape of a Decision changes, independently of the feature schema.
DECISION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Decision:
    """One logged score: its inputs, the function that produced it, the output, and when.

    :param features: The exact :class:`FeatureVector` the score was computed from.
    :param function_name: Identity of the scoring function (``ScoringFunction.name``).
    :param function_version: Version of that function at the time of the score.
    :param score: The validated delegation float in ``[0,1]``.
    :param timestamp: When the score was taken. Timezone-aware; normalised to UTC on construction.
    :param schema_version: The decision-record schema version; defaults to the current one.
    """

    features: FeatureVector
    function_name: str
    function_version: str
    score: float
    timestamp: datetime
    schema_version: int = field(default=DECISION_SCHEMA_VERSION)

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("Decision.timestamp must be timezone-aware")
        # Normalise to UTC so equality and the canonical encoding are stable regardless of offset.
        object.__setattr__(self, "timestamp", self.timestamp.astimezone(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "features": self.features.to_dict(),
            "function_name": self.function_name,
            "function_version": self.function_version,
            "score": self.score,
            "timestamp": _encode_timestamp(self.timestamp),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Decision:
        version = data.get("schema_version", DECISION_SCHEMA_VERSION)
        if version != DECISION_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported Decision schema_version {version!r}; "
                f"this build reads version {DECISION_SCHEMA_VERSION}"
            )
        return cls(
            features=FeatureVector.from_dict(data["features"]),
            function_name=data["function_name"],
            function_version=data["function_version"],
            score=data["score"],
            timestamp=_decode_timestamp(data["timestamp"]),
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
    def from_json(cls, text: str) -> Decision:
        return cls.from_dict(json.loads(text))


@runtime_checkable
class DecisionLog(Protocol):
    """Append-only sink for :class:`Decision`\\ s.

    Implementations must round-trip: appending a decision and reading it back yields an equal
    :class:`Decision`. Append is atomic per record.
    """

    def append(self, decision: Decision) -> None:
        """Append a single decision."""
        ...

    def scan(self) -> list[Decision]:
        """Every decision in the log, in append order."""
        ...


class InMemoryDecisionLog:
    """A :class:`DecisionLog` backed by an in-process list.

    The injectable default for tests: no filesystem, no git, nothing shared between instances, so a
    case can inject a fresh log and read back exactly what a score wrote.
    """

    def __init__(self) -> None:
        self._decisions: list[Decision] = []

    def append(self, decision: Decision) -> None:
        self._decisions.append(decision)

    def scan(self) -> list[Decision]:
        return list(self._decisions)

    def __len__(self) -> int:
        return len(self._decisions)

    def __iter__(self) -> Iterator[Decision]:
        return iter(self._decisions)


def _encode_timestamp(value: datetime) -> str:
    # Decision normalises to UTC on construction, so this is always a +00:00 instant; emit the
    # canonical 'Z' form to match the event log's encoding.
    return value.isoformat().replace("+00:00", "Z")


def _decode_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)
