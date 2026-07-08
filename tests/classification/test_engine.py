"""Unit tests for :class:`SelectorClassificationStrategy` and its conflict rule.

Covers the acceptance criteria that live in the engine: the ``**/*.test.ts`` in ``repo=checkout``
example, unmatched events, and the documented most-specific-then-priority conflict resolution
(including the ambiguous fail-toward-caution case).
"""

from __future__ import annotations

from sailguarding.classification import (
    Outcome,
    Selector,
    SelectorClassificationStrategy,
    SelectorRule,
)
from tests.classification.conftest import EventFactory

WRITE_TESTS = SelectorRule(
    selector=Selector(tool="Edit", path="**/*.test.ts", context={"repo": "checkout"}),
    activity_id="write-tests",
)


def test_matches_write_tests_in_checkout(make_event: EventFactory) -> None:
    engine = SelectorClassificationStrategy([WRITE_TESTS])
    event = make_event(tool_input={"file_path": "src/cart.test.ts"}, context={"repo": "checkout"})

    result = engine.classify(event)

    assert result.outcome is Outcome.MATCHED
    assert result.activity_id == "write-tests"


def test_same_edit_elsewhere_does_not_match(make_event: EventFactory) -> None:
    engine = SelectorClassificationStrategy([WRITE_TESTS])
    event = make_event(tool_input={"file_path": "src/cart.test.ts"}, context={"repo": "billing"})

    result = engine.classify(event)

    assert result.outcome is Outcome.UNMATCHED
    assert result.activity_id is None


def test_unmatched_when_no_rule_matches(make_event: EventFactory) -> None:
    engine = SelectorClassificationStrategy([WRITE_TESTS])
    result = engine.classify(make_event(tool_name="Bash", tool_input={"command": "ls"}))
    assert result.outcome is Outcome.UNMATCHED


def test_most_specific_selector_wins(make_event: EventFactory) -> None:
    broad = SelectorRule(selector=Selector(tool="Edit"), activity_id="edit-something")
    specific = SelectorRule(
        selector=Selector(tool="Edit", path="**/*.test.ts", context={"repo": "checkout"}),
        activity_id="write-tests",
    )
    # Registration order deliberately puts the broad rule first to prove order is irrelevant.
    engine = SelectorClassificationStrategy([broad, specific])
    event = make_event(tool_input={"file_path": "a.test.ts"}, context={"repo": "checkout"})

    result = engine.classify(event)

    assert result.outcome is Outcome.MATCHED
    assert result.activity_id == "write-tests"


def test_priority_breaks_specificity_ties(make_event: EventFactory) -> None:
    low = SelectorRule(selector=Selector(tool="Edit"), activity_id="low", priority=1)
    high = SelectorRule(selector=Selector(tool="Edit"), activity_id="high", priority=9)
    engine = SelectorClassificationStrategy([low, high])

    result = engine.classify(make_event(tool_name="Edit"))

    assert result.activity_id == "high"


def test_tie_on_same_action_is_not_a_conflict(make_event: EventFactory) -> None:
    # Two equally specific rules that name the *same* activity: resolve to it, no ambiguity.
    by_path = SelectorRule(selector=Selector(path="**/*.test.ts"), activity_id="write-tests")
    by_tool = SelectorRule(selector=Selector(tool="Edit"), activity_id="write-tests")
    engine = SelectorClassificationStrategy([by_path, by_tool])
    event = make_event(tool_name="Edit", tool_input={"file_path": "a.test.ts"})

    result = engine.classify(event)

    assert result.outcome is Outcome.MATCHED
    assert result.activity_id == "write-tests"


def test_ambiguous_when_top_rules_disagree(make_event: EventFactory) -> None:
    # Equal specificity, equal priority, different activities: fail toward caution — do not guess.
    a = SelectorRule(selector=Selector(tool="Edit"), activity_id="activity-a")
    b = SelectorRule(selector=Selector(context={"repo": "checkout"}), activity_id="activity-b")
    engine = SelectorClassificationStrategy([a, b])
    event = make_event(tool_name="Edit", context={"repo": "checkout"})

    result = engine.classify(event)

    assert result.outcome is Outcome.AMBIGUOUS
    assert result.activity_id is None
    assert result.candidates == ("activity-a", "activity-b")


def test_register_adds_a_rule(make_event: EventFactory) -> None:
    engine = SelectorClassificationStrategy()
    assert engine.classify(make_event()).outcome is Outcome.UNMATCHED

    engine.register(WRITE_TESTS)
    event = make_event(tool_input={"file_path": "a.test.ts"}, context={"repo": "checkout"})
    assert engine.classify(event).activity_id == "write-tests"
