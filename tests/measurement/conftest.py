"""Shared fixtures for the measurement tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from sailguarding.domain import Context
from sailguarding.measurement import Evidence
from sailguarding.safeguards import Measurement


@pytest.fixture
def evidence_factory() -> Callable[..., Evidence]:
    """Build an :class:`Evidence` record, overriding any field per case."""

    def _make(**over: object) -> Evidence:
        base: dict[str, object] = {
            "safeguard_id": "no-flaky-tests",
            "metric": "flakiness",
            "value": 0.01,
            "measures": Measurement.HEALTH,
            "context": Context(repo="checkout"),
            "timestamp": datetime(2026, 7, 5, 12, 0, tzinfo=UTC),
        }
        base.update(over)
        return Evidence(**base)  # type: ignore[arg-type]

    return _make
