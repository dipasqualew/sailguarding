"""Unit tests for the :class:`Matcher` and its triage routing.

These verify the orchestration seam: a resolved event comes back with ``action_id`` filled, an
unresolved one is routed to the triage queue and retrievable, and the strategy is injectable —
a stub replaces the selector engine wholesale.
"""

from __future__ import annotations

from sailguarding.classification import (
    Classification,
    Matcher,
    Outcome,
    Selector,
    SelectorClassificationStrategy,
    SelectorRule,
    TriageQueue,
)
from sailguarding.domain import EventRecord
from tests.classification.conftest import EventFactory

WRITE_TESTS = SelectorRule(
    selector=Selector(tool="Edit", path="**/*.test.ts", context={"repo": "checkout"}),
    action_id="write-tests",
)


class _StubStrategy:
    """A canned strategy proving the seam: it ignores the event and returns a fixed result."""

    def __init__(self, result: Classification) -> None:
        self._result = result
        self.seen: list[EventRecord] = []

    def classify(self, event: EventRecord) -> Classification:
        self.seen.append(event)
        return self._result


def test_resolved_event_gets_action_id_filled(make_event: EventFactory) -> None:
    matcher = Matcher(SelectorClassificationStrategy([WRITE_TESTS]))
    event = make_event(tool_input={"file_path": "a.test.ts"}, context={"repo": "checkout"})

    classified = matcher.classify(event)

    assert classified.action_id == "write-tests"
    assert len(matcher.triage) == 0
    # The input is untouched — classification returns a new record.
    assert event.action_id is None


def test_unmatched_event_lands_in_triage_and_is_retrievable(make_event: EventFactory) -> None:
    matcher = Matcher(SelectorClassificationStrategy([WRITE_TESTS]))
    event = make_event(tool_name="Bash", tool_input={"command": "ls"})

    classified = matcher.classify(event)

    assert classified.action_id is None
    pending = matcher.triage.pending()
    assert len(pending) == 1
    assert pending[0].event == event
    assert pending[0].reason is Outcome.UNMATCHED


def test_ambiguous_event_is_triaged_with_candidates() -> None:
    stub = _StubStrategy(Classification.ambiguous(("action-a", "action-b")))
    matcher = Matcher(stub)

    matcher.classify(_event())

    entry = matcher.triage.pending()[0]
    assert entry.reason is Outcome.AMBIGUOUS
    assert entry.candidates == ("action-a", "action-b")


def test_strategy_is_injected_not_hard_wired() -> None:
    stub = _StubStrategy(Classification.matched("stubbed"))
    matcher = Matcher(stub)

    classified = matcher.classify(_event())

    assert classified.action_id == "stubbed"
    assert stub.seen  # the stub really ran in place of the selector engine


def test_shared_triage_queue_accumulates(make_event: EventFactory) -> None:
    triage = TriageQueue()
    matcher = Matcher(SelectorClassificationStrategy([WRITE_TESTS]), triage=triage)

    matcher.classify(make_event(tool_name="Bash", tool_input={"command": "ls"}))
    matcher.classify(make_event(tool_name="Read", tool_input={"file_path": "x.md"}))

    assert len(triage) == 2


def test_classify_all_preserves_order_and_triages_the_rest(make_event: EventFactory) -> None:
    matcher = Matcher(SelectorClassificationStrategy([WRITE_TESTS]))
    resolved = make_event(tool_input={"file_path": "a.test.ts"}, context={"repo": "checkout"})
    unmatched = make_event(tool_name="Bash", tool_input={"command": "ls"})

    out = matcher.classify_all([resolved, unmatched])

    assert [e.action_id for e in out] == ["write-tests", None]
    assert len(matcher.triage) == 1


def _event() -> EventRecord:
    from datetime import UTC, datetime

    from sailguarding.domain import Context

    return EventRecord(
        session_id="s",
        harness_id="claude-code",
        tool_name="Edit",
        tool_input={"file_path": "a.ts"},
        context=Context(repo="checkout"),
        timestamp=datetime(2026, 7, 5, tzinfo=UTC),
    )
