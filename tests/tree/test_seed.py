"""Unit tests for bottom-up seeding: a triaged event → a named action + a matching selector."""

from __future__ import annotations

from datetime import UTC, datetime

from sailguarding.classification import (
    Outcome,
    SelectorClassificationStrategy,
    TriageEntry,
)
from sailguarding.domain import Action, Context, EventRecord
from sailguarding.tree import ActionTree, seed_action, seeded_rules, selector_for_event


def _event(tool: str, tool_input: dict[str, object]) -> EventRecord:
    return EventRecord(
        session_id="s",
        harness_id="claude-code",
        tool_name=tool,
        tool_input=tool_input,
        context=Context(repo="checkout", team="core"),
        timestamp=datetime(2026, 7, 5, 12, 0, tzinfo=UTC),
    )


def _entry(event: EventRecord) -> TriageEntry:
    return TriageEntry(event=event, reason=Outcome.UNMATCHED)


def test_selector_for_a_path_event_keys_on_tool_path_and_context() -> None:
    selector = selector_for_event(_event("Edit", {"file_path": "src/cart.test.ts"}))
    assert selector.tool == "Edit"
    assert selector.path == "src/cart.test.ts"
    assert selector.command is None
    assert selector.context == {"repo": "checkout", "team": "core"}


def test_selector_for_a_command_event_keys_on_the_command() -> None:
    selector = selector_for_event(_event("Bash", {"command": "npm run deploy:staging"}))
    assert selector.tool == "Bash"
    assert selector.path is None
    assert selector.command == "npm run deploy:staging"


def test_synthesised_selector_matches_the_event_it_came_from() -> None:
    event = _event("Edit", {"file_path": "src/cart.test.ts"})
    assert selector_for_event(event).matches(event)


def test_seed_action_produces_a_node_and_a_recognising_rule() -> None:
    event = _event("Edit", {"file_path": "src/cart.test.ts"})
    seed = seed_action(_entry(event), action_id="write-tests", label="write the tests")

    assert seed.action == Action(id="write-tests", label="write the tests")
    assert seed.rule.action_id == "write-tests"
    assert seed.rule.selector.matches(event)


def test_seed_action_reparents_and_grafts_into_the_tree() -> None:
    tree = ActionTree(Action(id="ship-update", label="ship the update"))
    event = _event("Edit", {"file_path": "src/cart.test.ts"})

    seed = seed_action(
        _entry(event), action_id="write-tests", label="write the tests", parent_id="ship-update"
    )
    grown = tree.graft("ship-update", seed.action)

    node = grown.find("write-tests")
    assert node is not None
    assert node.parent_id == "ship-update"


def test_seeded_rule_makes_the_classifier_resolve_the_once_unmatched_event() -> None:
    event = _event("Edit", {"file_path": "src/cart.test.ts"})

    # Before: nothing matches, the event is triaged.
    empty = SelectorClassificationStrategy(())
    assert empty.classify(event).outcome is Outcome.UNMATCHED

    # Seed an action from the triaged event, then classify with the synthesised rule.
    seed = seed_action(_entry(event), action_id="write-tests", label="write the tests")
    strategy = SelectorClassificationStrategy(seeded_rules([seed]))
    result = strategy.classify(event)
    assert result.outcome is Outcome.MATCHED
    assert result.action_id == "write-tests"
