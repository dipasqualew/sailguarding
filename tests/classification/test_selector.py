"""Unit tests for the :class:`Selector` language.

These pin the declarative predicate: tool/path/command attributes and context labels, the two
glob dialects (``**``-aware paths vs. flat fnmatch elsewhere), specificity scoring, and
round-trip serialisation.
"""

from __future__ import annotations

import pytest

from sailguarding.classification import Selector, SelectorRule
from tests.classification.conftest import EventFactory


def test_empty_selector_matches_anything(make_event: EventFactory) -> None:
    assert Selector().matches(make_event()) is True


def test_tool_name_glob(make_event: EventFactory) -> None:
    assert Selector(tool="Edit").matches(make_event(tool_name="Edit")) is True
    assert Selector(tool="Edit").matches(make_event(tool_name="Bash")) is False
    assert Selector(tool="*").matches(make_event(tool_name="Anything")) is True


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        pytest.param("**/*.test.ts", "foo.test.ts", True, id="bare-file"),
        pytest.param("**/*.test.ts", "src/a/b.test.ts", True, id="nested"),
        pytest.param("**/*.test.ts", "src/foo.ts", False, id="not-a-test"),
        pytest.param("*.ts", "foo.ts", True, id="single-star-in-segment"),
        pytest.param("*.ts", "src/foo.ts", False, id="single-star-does-not-cross-slash"),
        pytest.param("src/**/*.py", "src/a/b/c.py", True, id="double-star-mid"),
        pytest.param("src/*.py", "src/foo.py", True, id="segment-glob"),
    ],
)
def test_path_glob_semantics(
    make_event: EventFactory, pattern: str, path: str, expected: bool
) -> None:
    event = make_event(tool_input={"file_path": path})
    assert Selector(path=pattern).matches(event) is expected


def test_path_selector_misses_event_without_a_path(make_event: EventFactory) -> None:
    # A Bash command carries no file path, so a path selector cannot match it — this is the
    # documented v1 weakness (a command that writes code slips a path glob).
    event = make_event(tool_name="Bash", tool_input={"command": "echo x > hello.py"})
    assert Selector(path="**/*.py").matches(event) is False


def test_path_read_from_alternate_keys(make_event: EventFactory) -> None:
    assert Selector(path="a.ipynb").matches(make_event(tool_input={"notebook_path": "a.ipynb"}))
    assert Selector(path="a.txt").matches(make_event(tool_input={"path": "a.txt"}))


def test_command_glob(make_event: EventFactory) -> None:
    event = make_event(tool_name="Bash", tool_input={"command": "npm test"})
    assert Selector(command="npm test").matches(event) is True
    assert Selector(command="npm *").matches(event) is True
    assert Selector(command="git *").matches(event) is False


def test_command_matching_is_case_sensitive(make_event: EventFactory) -> None:
    event = make_event(tool_name="Bash", tool_input={"command": "npm test"})
    assert Selector(command="NPM *").matches(event) is False


def test_context_label_exact_and_wildcard(make_event: EventFactory) -> None:
    event = make_event(context={"repo": "checkout", "team": "core"})
    assert Selector(context={"repo": "checkout"}).matches(event) is True
    assert Selector(context={"repo": "billing"}).matches(event) is False
    assert Selector(context={"team": "*"}).matches(event) is True


def test_context_wildcard_requires_dimension_present(make_event: EventFactory) -> None:
    event = make_event(context={"repo": "checkout"})
    # 'team=*' means "has a team, any value" — an event without the dimension does not match.
    assert Selector(context={"team": "*"}).matches(event) is False


def test_context_value_coerced_to_string(make_event: EventFactory) -> None:
    event = make_event(context={"attempt": 3, "prod": True})
    assert Selector(context={"attempt": "3"}).matches(event) is True
    assert Selector(context={"prod": "True"}).matches(event) is True


def test_all_set_fields_must_hold(make_event: EventFactory) -> None:
    event = make_event(
        tool_name="Edit",
        tool_input={"file_path": "a.test.ts"},
        context={"repo": "checkout"},
    )
    both = Selector(tool="Edit", path="**/*.test.ts", context={"repo": "checkout"})
    assert both.matches(event) is True
    # Flip only the context: the AND fails.
    assert (
        Selector(tool="Edit", path="**/*.test.ts", context={"repo": "billing"}).matches(event)
        is False
    )


def test_context_mapping_is_copied_defensively() -> None:
    labels = {"repo": "checkout"}
    selector = Selector(context=labels)
    labels["repo"] = "billing"
    assert selector.context == {"repo": "checkout"}


@pytest.mark.parametrize(
    ("selector", "expected"),
    [
        pytest.param(Selector(), 0, id="empty"),
        pytest.param(Selector(tool="Edit"), 1, id="one-attr"),
        pytest.param(Selector(tool="*"), 0, id="universal-tool-scores-zero"),
        pytest.param(Selector(context={"team": "*"}), 0, id="universal-label-scores-zero"),
        pytest.param(
            Selector(tool="Edit", path="**/*.test.ts", context={"repo": "checkout", "team": "*"}),
            3,
            id="two-attrs-one-real-label",
        ),
    ],
)
def test_specificity(selector: Selector, expected: int) -> None:
    assert selector.specificity == expected


def test_selector_round_trips() -> None:
    selector = Selector(tool="Edit", path="**/*.test.ts", context={"repo": "checkout"})
    assert Selector.from_dict(selector.to_dict()) == selector


def test_selector_to_dict_omits_unset_fields() -> None:
    assert Selector(tool="Edit").to_dict() == {"tool": "Edit"}


def test_rule_round_trips() -> None:
    rule = SelectorRule(
        selector=Selector(tool="Edit", context={"repo": "checkout"}),
        action_id="write-tests",
        priority=5,
    )
    assert SelectorRule.from_dict(rule.to_dict()) == rule
