"""Unit tests for :class:`sailguarding.domain.EventRecord`.

The record is captured before classification, so ``action_id`` is nullable and defaults to
``None``. Timestamps must be timezone-aware and are normalised to UTC on construction.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from sailguarding.domain import SCHEMA_VERSION, Context, EventRecord


def _event(timestamp: datetime, **overrides: object) -> EventRecord:
    kwargs: dict[str, object] = {
        "session_id": "session-1",
        "harness_id": "claude-code",
        "tool_name": "Edit",
        "tool_input": {"file_path": "checkout.py"},
        "context": Context(repo="checkout"),
        "timestamp": timestamp,
    }
    kwargs.update(overrides)
    return EventRecord(**kwargs)  # type: ignore[arg-type]


def test_action_id_defaults_to_none() -> None:
    event = _event(datetime(2026, 7, 5, 12, 0, tzinfo=UTC))

    assert event.action_id is None


def test_schema_version_defaults_to_current() -> None:
    event = _event(datetime(2026, 7, 5, 12, 0, tzinfo=UTC))

    assert event.schema_version == SCHEMA_VERSION


def test_resolved_action_id_is_kept() -> None:
    event = _event(datetime(2026, 7, 5, 12, 0, tzinfo=UTC), action_id="write-tests")

    assert event.action_id == "write-tests"


def test_naive_timestamp_raises_value_error() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _event(datetime(2026, 7, 5, 12, 0))  # intentionally naive (no tzinfo)


@pytest.mark.parametrize(
    ("input_timestamp", "expected_utc"),
    [
        pytest.param(
            datetime(2026, 7, 5, 14, 30, tzinfo=timezone(timedelta(hours=2))),
            datetime(2026, 7, 5, 12, 30, tzinfo=UTC),
            id="plus-two",
        ),
        pytest.param(
            datetime(2026, 7, 5, 7, 30, tzinfo=timezone(timedelta(hours=-5))),
            datetime(2026, 7, 5, 12, 30, tzinfo=UTC),
            id="minus-five",
        ),
        pytest.param(
            datetime(2026, 7, 5, 12, 30, tzinfo=UTC),
            datetime(2026, 7, 5, 12, 30, tzinfo=UTC),
            id="already-utc",
        ),
    ],
)
def test_timestamp_normalised_to_utc(input_timestamp: datetime, expected_utc: datetime) -> None:
    event = _event(input_timestamp)

    # Same instant, expressed in UTC.
    assert event.timestamp == input_timestamp
    assert event.timestamp == expected_utc
    assert event.timestamp.tzinfo == UTC
    assert event.timestamp.utcoffset() == timedelta(0)


def test_equal_events_from_different_offsets_are_equal() -> None:
    utc = _event(datetime(2026, 7, 5, 12, 30, tzinfo=UTC))
    offset = _event(datetime(2026, 7, 5, 14, 30, tzinfo=timezone(timedelta(hours=2))))

    assert utc == offset


def test_event_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    event = _event(datetime(2026, 7, 5, 12, 0, tzinfo=UTC))
    with pytest.raises(FrozenInstanceError):
        event.session_id = "other"  # type: ignore[misc]
