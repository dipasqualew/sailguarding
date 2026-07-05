"""Shared fixtures for the sensor tests.

The centre of gravity is the deterministic path: a :class:`MockClaudeCode` driving the sensor
with an injected in-memory sink, a :class:`FrozenGit`, and a frozen clock, so a test can assert
the captured :class:`EventRecord` byte-for-byte with no live session and no git branch.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from sailguarding.sensor.mock import FrozenGit, MockClaudeCode
from sailguarding.storage import InMemoryStorage

# A fixed instant every deterministic assertion is pinned to.
FROZEN_NOW = datetime(2026, 7, 5, 12, 30, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> Callable[[], datetime]:
    """A frozen clock so captured timestamps are deterministic."""
    return lambda: FROZEN_NOW


@pytest.fixture
def sink() -> InMemoryStorage:
    """A fresh in-memory sink injected into the sensor path."""
    return InMemoryStorage()


@pytest.fixture
def frozen_git() -> FrozenGit:
    """A fake git returning a fixed repo / branch / commit — no real git required."""
    return FrozenGit(
        toplevel="/work/checkout",
        branch="feature/pricing",
        commit="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
    )


@pytest.fixture
def mock() -> MockClaudeCode:
    """A Claude Code stand-in whose tool calls run in the fake repo's working directory."""
    return MockClaudeCode(cwd="/work/checkout", session_id="session-1")
