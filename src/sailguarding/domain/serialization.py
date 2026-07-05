"""The single canonical JSON encoding for :class:`EventRecord`.

This module is the one place that knows how an event becomes bytes. Task 02 writes these
lines as JSONL; anything that reads the log parses them here. The encoding is *canonical*:
keys are sorted and separators are tight, so the same record always produces byte-identical
output — a git-native, diff-friendly, append-only log.

Round-trip identity holds: ``event_from_json(event_to_json(e)) == e``.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sailguarding.domain.context import Context
from sailguarding.domain.event import SCHEMA_VERSION, EventRecord


def event_to_dict(event: EventRecord) -> dict[str, Any]:
    """Convert an event to a plain JSON-compatible dict."""
    return {
        "schema_version": event.schema_version,
        "timestamp": _encode_timestamp(event.timestamp),
        "session_id": event.session_id,
        "harness_id": event.harness_id,
        "tool_name": event.tool_name,
        "tool_input": dict(event.tool_input),
        "context": dict(event.context),
        "action_id": event.action_id,
    }


def event_from_dict(data: dict[str, Any]) -> EventRecord:
    """Rebuild an event from a dict produced by :func:`event_to_dict`."""
    try:
        version = data["schema_version"]
    except KeyError as exc:
        raise ValueError("event is missing required field 'schema_version'") from exc
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported EventRecord schema_version {version!r}; "
            f"this build reads version {SCHEMA_VERSION}"
        )

    return EventRecord(
        session_id=data["session_id"],
        harness_id=data["harness_id"],
        tool_name=data["tool_name"],
        tool_input=data["tool_input"],
        context=Context(data["context"]),
        timestamp=_decode_timestamp(data["timestamp"]),
        action_id=data.get("action_id"),
        schema_version=version,
    )


def event_to_json(event: EventRecord) -> str:
    """Serialise an event to a canonical, single-line JSON string."""
    return json.dumps(
        event_to_dict(event),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def event_from_json(text: str) -> EventRecord:
    """Parse an event from a JSON string produced by :func:`event_to_json`."""
    return event_from_dict(json.loads(text))


def _encode_timestamp(value: datetime) -> str:
    # EventRecord normalises to UTC on construction, so this is always a +00:00 instant;
    # emit it as the canonical 'Z' form.
    return value.isoformat().replace("+00:00", "Z")


def _decode_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)
