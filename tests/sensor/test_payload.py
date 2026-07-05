"""Parsing and validating the pinned PreToolUse hook contract."""

from __future__ import annotations

import pytest

from sailguarding.sensor.payload import HookPayloadError, parse_payload


def _valid() -> dict[str, object]:
    return {
        "session_id": "abc123",
        "transcript_path": "/home/user/.claude/t.jsonl",
        "cwd": "/home/user/project",
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
    }


def test_parses_a_full_pre_tool_use_payload() -> None:
    payload = parse_payload(_valid())

    assert payload.session_id == "abc123"
    assert payload.tool_name == "Bash"
    assert payload.tool_input == {"command": "ls"}
    assert payload.cwd == "/home/user/project"
    assert payload.hook_event_name == "PreToolUse"
    assert payload.transcript_path == "/home/user/.claude/t.jsonl"
    assert payload.permission_mode == "default"


def test_optional_fields_default_to_none() -> None:
    data = _valid()
    del data["transcript_path"]
    del data["permission_mode"]

    payload = parse_payload(data)

    assert payload.transcript_path is None
    assert payload.permission_mode is None


def test_missing_hook_event_name_is_assumed_pre_tool_use() -> None:
    data = _valid()
    del data["hook_event_name"]

    assert parse_payload(data).hook_event_name == "PreToolUse"


@pytest.mark.parametrize("field", ["session_id", "tool_name", "cwd"])
def test_missing_required_field_raises(field: str) -> None:
    data = _valid()
    del data[field]

    with pytest.raises(HookPayloadError, match=field):
        parse_payload(data)


def test_wrong_event_name_raises() -> None:
    data = _valid()
    data["hook_event_name"] = "PostToolUse"

    with pytest.raises(HookPayloadError, match="PreToolUse"):
        parse_payload(data)


def test_non_object_tool_input_raises() -> None:
    data = _valid()
    data["tool_input"] = "not-an-object"

    with pytest.raises(HookPayloadError, match="tool_input"):
        parse_payload(data)


def test_missing_tool_input_defaults_to_empty() -> None:
    data = _valid()
    del data["tool_input"]

    assert parse_payload(data).tool_input == {}
