"""The append-only observation the sensor writes and everything downstream reads.

An ``EventRecord`` is captured at pre-tool-use time, before classification runs, which is
why ``activity_id`` is nullable: the sensor records *what the agent did*; resolving it to an
activity, and joining outcomes, happens later. The schema is deliberately domain-agnostic —
it describes "a tool wrote to a file in this repo" and, unchanged, "an agent placed an
order for this home".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sailguarding.domain.context import Context

# Bumped whenever the on-disk shape of an EventRecord changes. Written into every record
# so a reader can migrate old logs. v2 renamed the resolved-action key ``action_id`` to
# ``activity_id`` (the Action → Activity rename); v1 logs are not read by this build.
SCHEMA_VERSION = 2


@dataclass(frozen=True)
class EventRecord:
    """One observed tool event with the context it ran in.

    :param session_id: The harness session the event belongs to.
    :param harness_id: Which adapter produced it (e.g. ``"claude-code"``).
    :param tool_name: Raw tool name as the harness reported it (e.g. ``"Edit"``).
    :param tool_input: Raw tool input, as a JSON-serialisable mapping. Stored verbatim.
    :param context: Resolved context the event ran in.
    :param timestamp: When the event was observed. Must be timezone-aware; normalised to
        UTC on construction.
    :param activity_id: The resolved activity, or ``None`` when unclassified (the default at
        capture time).
    :param schema_version: The record schema version; defaults to the current one.
    """

    session_id: str
    harness_id: str
    tool_name: str
    tool_input: Mapping[str, Any]
    context: Context
    timestamp: datetime
    activity_id: str | None = None
    schema_version: int = field(default=SCHEMA_VERSION)

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("EventRecord.timestamp must be timezone-aware")
        # Normalise to UTC so equality and the canonical encoding are stable regardless of
        # the originating offset. object.__setattr__ because the dataclass is frozen.
        object.__setattr__(self, "timestamp", self.timestamp.astimezone(UTC))
