"""Shared fixtures for the domain tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sailguarding.domain import Context, EventRecord


@pytest.fixture
def sample_event() -> EventRecord:
    """A representative, already-UTC event used across serialization tests."""
    return EventRecord(
        session_id="session-1",
        harness_id="claude-code",
        tool_name="Edit",
        tool_input={"file_path": "checkout.py", "content": "print('hi')"},
        context=Context(team="core", repo="checkout"),
        timestamp=datetime(2026, 7, 5, 12, 30, 0, tzinfo=UTC),
        action_id=None,
    )
