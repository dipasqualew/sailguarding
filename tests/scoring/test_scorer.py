"""The execution seam: run an injected function, validate, log — or reject and log nothing."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sailguarding.scoring import (
    FeatureVector,
    InMemoryDecisionLog,
    InvalidScore,
    SafeguardSignal,
    Scorer,
)
from tests.scoring.conftest import StubFactory

FIXED_CLOCK = lambda: datetime(2026, 7, 5, 12, 30, tzinfo=UTC)  # noqa: E731

FEATURES = FeatureVector(
    signals=(SafeguardSignal("no-flaky-tests", "flakiness", 0.004),),
    remaining_budget=0.9,
    action_id="write-tests",
)


def test_stub_function_scores_without_any_real_model(make_function: StubFactory) -> None:
    scorer = Scorer(make_function(0.75), clock=FIXED_CLOCK)
    decision = scorer.score(FEATURES)
    assert decision.score == 0.75


def test_every_score_writes_one_decision_log_entry(make_function: StubFactory) -> None:
    log = InMemoryDecisionLog()
    scorer = Scorer(make_function(0.6, name="team-fn", version="3"), log, clock=FIXED_CLOCK)

    returned = scorer.score(FEATURES)

    assert log.scan() == [returned]
    entry = log.scan()[0]
    assert entry.features == FEATURES
    assert entry.function_name == "team-fn"
    assert entry.function_version == "3"
    assert entry.score == 0.6
    assert entry.timestamp == datetime(2026, 7, 5, 12, 30, tzinfo=UTC)


def test_out_of_range_output_is_rejected_and_nothing_is_logged(make_function: StubFactory) -> None:
    log = InMemoryDecisionLog()
    scorer = Scorer(make_function(1.7), log, clock=FIXED_CLOCK)

    with pytest.raises(InvalidScore):
        scorer.score(FEATURES)

    assert log.scan() == []  # a rejected score never reaches the audit trail


def test_non_finite_output_is_rejected(make_function: StubFactory) -> None:
    scorer = Scorer(make_function(float("nan")), clock=FIXED_CLOCK)
    with pytest.raises(InvalidScore, match="non-finite"):
        scorer.score(FEATURES)


def test_scorer_defaults_to_its_own_in_memory_log(make_function: StubFactory) -> None:
    scorer = Scorer(make_function(0.5), clock=FIXED_CLOCK)
    scorer.score(FEATURES)
    assert scorer.log.scan()[0].score == 0.5
