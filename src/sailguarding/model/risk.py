"""The reusable risk — a named hazard an activity can face, that a safeguard mitigates.

A :class:`Risk` is a **library entity**, not a property of one activity. "data loss", "break
capabilities", "opportunity cost" are risks a team names once and then *references* from many
activities: the same "data loss" risk hangs off "run the migration" and off "prune the backups".
Modelling it as a shared, id'd record — rather than a string repeated on each node — is what lets
the governance model count reuse ("how many activities face this risk?") and attach a mitigation
once.

A risk carries no scoring of its own: *how bad* it is, and *how much* a safeguard offsets it, live
in the team's scoring function, not here. This type is only the shared vocabulary — the noun a
:class:`~sailguarding.safeguards.Safeguard` is declared to mitigate.

Like every other on-disk shape in the engine, :class:`Risk` is **versioned, serialisable, and
round-trip stable** (``Risk.from_json(r.to_json()) == r``), and deliberately **domain-agnostic**:
the same record names a hazard of a code edit ("break capabilities") and of a sofa purchase
("overspend the budget").
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

# Bumped whenever the serialised shape of a Risk changes, so a reader can tell which schema produced
# a stored record.
RISK_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Risk:
    """A named hazard an activity can face, referenced by id from the governance model.

    :param id: Stable identifier, referenced by an activity's risk edge and by every mitigation
        (e.g. ``"data-loss"``).
    :param label: Human-readable name for dashboards and audit trails (e.g. ``"Data loss"``).
    :param description: Optional longer explanation of the hazard; empty by default.
    :param schema_version: The record schema version; defaults to the current one.
    """

    id: str
    label: str
    description: str = ""
    schema_version: int = field(default=RISK_SCHEMA_VERSION)

    def to_dict(self) -> dict[str, Any]:
        """A JSON-compatible dict."""
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "label": self.label,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Risk:
        """Rebuild a risk from :meth:`to_dict` output, rejecting an unknown schema version."""
        version = data.get("schema_version", RISK_SCHEMA_VERSION)
        if version != RISK_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported Risk schema_version {version!r}; "
                f"this build reads version {RISK_SCHEMA_VERSION}"
            )
        return cls(
            id=data["id"],
            label=data["label"],
            description=data.get("description", ""),
            schema_version=version,
        )

    def to_json(self) -> str:
        """Serialise to a canonical, single-line JSON string (sorted keys, tight separators)."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> Risk:
        """Parse a risk from a JSON string produced by :meth:`to_json`."""
        return cls.from_dict(json.loads(text))
