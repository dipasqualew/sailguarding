"""Shared fixtures for the classification tests."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

import pytest

from sailguarding.domain import Context, EventRecord

EventFactory = Callable[..., EventRecord]


@pytest.fixture
def make_event() -> EventFactory:
    """Build an :class:`EventRecord` with sensible defaults, overriding only what a case needs."""

    def _make(
        *,
        tool_name: str = "Edit",
        tool_input: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
        session_id: str = "session-1",
        harness_id: str = "claude-code",
    ) -> EventRecord:
        input_ = tool_input if tool_input is not None else {"file_path": "src/foo.py"}
        labels = context if context is not None else {"repo": "checkout", "team": "core"}
        return EventRecord(
            session_id=session_id,
            harness_id=harness_id,
            tool_name=tool_name,
            tool_input=dict(input_),
            context=Context(labels),
            timestamp=datetime(2026, 7, 5, 12, 30, 0, tzinfo=UTC),
        )

    return _make
