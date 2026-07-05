"""The pre-tool-use invocation as Claude Code hands it to a hook.

This is the *pinned contract* between the real harness and the sensor. Claude Code fires a
PreToolUse hook **before** a tool runs and writes a JSON object to the hook's stdin
describing *what the agent intends to do* — never whether it worked. :class:`HookPayload`
is exactly that object, parsed and validated, so the plugin and the deterministic mock
cannot silently drift from the harness.

The field set is taken from the Claude Code hooks reference (PreToolUse): the common
``session_id`` / ``transcript_path`` / ``cwd`` / ``permission_mode`` / ``hook_event_name``
fields plus the PreToolUse-specific ``tool_name`` and ``tool_input``. Unknown extra fields
are ignored on purpose — the harness may add more over time and a sensor must not break when
it does.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# The one hook event this sensor handles. Anything else is a misconfiguration.
PRE_TOOL_USE = "PreToolUse"


class HookPayloadError(ValueError):
    """The stdin payload was not a well-formed PreToolUse invocation."""


@dataclass(frozen=True)
class HookPayload:
    """A parsed PreToolUse invocation.

    :param session_id: The Claude Code session the tool call belongs to.
    :param tool_name: Raw tool name the agent is about to invoke (e.g. ``"Edit"``).
    :param tool_input: Raw tool arguments, exactly as the harness reported them.
    :param cwd: The working directory the tool runs in — the anchor for git context.
    :param hook_event_name: Always ``"PreToolUse"``; validated on parse.
    :param transcript_path: Path to the conversation transcript, when supplied.
    :param permission_mode: The active permission mode, when supplied.
    """

    session_id: str
    tool_name: str
    tool_input: Mapping[str, Any]
    cwd: str
    hook_event_name: str = PRE_TOOL_USE
    transcript_path: str | None = None
    permission_mode: str | None = None


def parse_payload(data: Mapping[str, Any]) -> HookPayload:
    """Validate and build a :class:`HookPayload` from a decoded stdin object.

    Raises :class:`HookPayloadError` if a required field is missing or the wrong shape, or
    the event is not a PreToolUse invocation. Callers run this behind the sensor's
    fail-open boundary, so a bad payload is logged and dropped, never raised at the agent.
    """
    if not isinstance(data, Mapping):
        raise HookPayloadError(f"hook payload must be a JSON object, got {type(data).__name__}")

    event = data.get("hook_event_name", PRE_TOOL_USE)
    if event != PRE_TOOL_USE:
        raise HookPayloadError(f"expected a {PRE_TOOL_USE} payload, got {event!r}")

    session_id = _require_str(data, "session_id")
    tool_name = _require_str(data, "tool_name")
    cwd = _require_str(data, "cwd")

    tool_input = data.get("tool_input", {})
    if not isinstance(tool_input, Mapping):
        raise HookPayloadError(
            f"'tool_input' must be a JSON object, got {type(tool_input).__name__}"
        )

    return HookPayload(
        session_id=session_id,
        tool_name=tool_name,
        tool_input=dict(tool_input),
        cwd=cwd,
        hook_event_name=event,
        transcript_path=_optional_str(data, "transcript_path"),
        permission_mode=_optional_str(data, "permission_mode"),
    )


def _require_str(data: Mapping[str, Any], key: str) -> str:
    try:
        value = data[key]
    except KeyError as exc:
        raise HookPayloadError(f"hook payload is missing required field {key!r}") from exc
    if not isinstance(value, str) or not value:
        raise HookPayloadError(f"hook payload field {key!r} must be a non-empty string")
    return value


def _optional_str(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise HookPayloadError(f"hook payload field {key!r} must be a string when present")
    return value
