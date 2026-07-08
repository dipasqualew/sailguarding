"""Decision-log record: auditable, round-trip stable, UTC-normalised."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from sailguarding.domain import Context
from sailguarding.scoring import (
    Decision,
    FeatureVector,
    InMemoryDecisionLog,
    SafeguardSignal,
)


def _decision() -> Decision:
    return Decision(
        features=FeatureVector(
            signals=(SafeguardSignal("no-flaky-tests", "flakiness", 0.004),),
            context=Context(repo="checkout"),
            remaining_budget=0.9,
            activity_id="write-tests",
        ),
        function_name="min-composition",
        function_version="1",
        score=0.9,
        timestamp=datetime(2026, 7, 5, 12, 30, tzinfo=UTC),
    )


def test_round_trips_through_json() -> None:
    decision = _decision()
    assert Decision.from_json(decision.to_json()) == decision


def test_read_back_reproduces_the_inputs_exactly() -> None:
    decision = _decision()
    restored = Decision.from_json(decision.to_json())
    # The whole point of the log: the stored decision reproduces the exact scoring inputs.
    assert restored.features == decision.features
    assert restored.function_name == "min-composition"
    assert restored.function_version == "1"
    assert restored.score == 0.9


def test_timestamp_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Decision(
            features=FeatureVector(),
            function_name="fn",
            function_version="1",
            score=0.5,
            timestamp=datetime(2026, 7, 5, 12, 30),  # naive
        )


def test_timestamp_is_normalised_to_utc() -> None:
    plus_two = timezone(timedelta(hours=2))
    decision = Decision(
        features=FeatureVector(),
        function_name="fn",
        function_version="1",
        score=0.5,
        timestamp=datetime(2026, 7, 5, 14, 30, tzinfo=plus_two),
    )
    assert decision.timestamp == datetime(2026, 7, 5, 12, 30, tzinfo=UTC)
    assert "Z" in decision.to_json()


def test_in_memory_log_appends_and_scans_in_order() -> None:
    log = InMemoryDecisionLog()
    first = _decision()
    second = Decision.from_dict({**first.to_dict(), "score": 0.1})

    log.append(first)
    log.append(second)

    assert len(log) == 2
    assert log.scan() == [first, second]
    assert list(log) == [first, second]
