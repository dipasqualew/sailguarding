"""The redaction seam: secret-bearing tool input is masked; everything else survives."""

from __future__ import annotations

from sailguarding.sensor.redaction import (
    REDACTED,
    PassthroughRedactor,
    SecretKeyRedactor,
)


def test_passthrough_stores_input_verbatim() -> None:
    tool_input = {"file_path": "a.py", "token": "sk-live-123"}

    assert PassthroughRedactor().redact("Edit", tool_input) == tool_input


def test_masks_values_of_secret_keys() -> None:
    result = SecretKeyRedactor().redact(
        "Bash", {"command": "deploy", "api_key": "sk-live", "PASSWORD": "hunter2"}
    )

    assert result["command"] == "deploy"
    assert result["api_key"] == REDACTED
    assert result["PASSWORD"] == REDACTED  # matching is case-insensitive


def test_recurses_into_nested_objects_and_lists() -> None:
    result = SecretKeyRedactor().redact(
        "Http",
        {
            "headers": {"Authorization": "Bearer x", "Accept": "json"},
            "retries": [{"secret": "s"}, {"attempt": 1}],
        },
    )

    assert result["headers"] == {"Authorization": REDACTED, "Accept": "json"}
    assert result["retries"] == [{"secret": REDACTED}, {"attempt": 1}]


def test_configured_extra_patterns_extend_the_defaults() -> None:
    # A team adds its own secret key without losing the built-in set.
    redactor = SecretKeyRedactor(patterns=("session_cookie",))

    result = redactor.redact("Edit", {"session_cookie": "abc", "path": "a.py"})

    assert result["session_cookie"] == REDACTED
    assert result["path"] == "a.py"


def test_non_secret_input_is_returned_unchanged() -> None:
    tool_input = {"file_path": "checkout.py", "content": "print('hi')"}

    assert SecretKeyRedactor().redact("Edit", tool_input) == tool_input
