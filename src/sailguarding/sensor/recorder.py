"""The sensor core: turn one PreToolUse invocation into a persisted :class:`EventRecord`.

This is the whole job of the sensor, and it is deliberately tiny and pure: resolve the context
the tool call ran in, redact its input, stamp the harness metadata, and append the record to a
storage strategy. Everything it depends on — the sink, the context resolver, the redactor, the
clock — is injected, so the same function drives a live branch sink in production and an
in-memory sink under the deterministic mock, with no branch in the code between the two.

The record is captured with ``activity_id`` null: this is pre-tool-use, before classification
runs (task 04) and before any outcome exists (evidence ingestion, later). The sensor records
*what the agent intends to do*; resolving it to an activity and joining an outcome happen later.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sailguarding.domain import EventRecord
from sailguarding.sensor.context import ContextResolver
from sailguarding.sensor.payload import HookPayload
from sailguarding.sensor.redaction import Redactor

# The harness this adapter speaks for. Stamped on every record so a multi-harness log stays
# attributable.
HARNESS_ID = "claude-code"


def record_event(
    payload: HookPayload,
    *,
    storage_append: Callable[[EventRecord], None],
    context_resolver: ContextResolver,
    redactor: Redactor,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> EventRecord:
    """Build the :class:`EventRecord` for ``payload`` and append it via ``storage_append``.

    Returns the record it wrote so callers (and tests) can assert on exactly what was captured.
    """
    context = context_resolver.resolve(payload)
    tool_input = redactor.redact(payload.tool_name, payload.tool_input)

    record = EventRecord(
        session_id=payload.session_id,
        harness_id=HARNESS_ID,
        tool_name=payload.tool_name,
        tool_input=tool_input,
        context=context,
        timestamp=clock(),
        activity_id=None,
    )
    storage_append(record)
    return record
