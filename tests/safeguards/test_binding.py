"""The :class:`SafeguardBinding`: matching over ``(action, context)`` and round-trip."""

from __future__ import annotations

from sailguarding.classification import Selector
from sailguarding.domain import Context
from sailguarding.safeguards import (
    Measurement,
    Safeguard,
    SafeguardBinding,
    SafeguardKind,
)

_SG = Safeguard(
    id="no-flaky-tests",
    label="No flaky tests",
    metric="flakiness",
    kind=SafeguardKind.STRUCTURAL,
    measures=Measurement.HEALTH,
)


def _binding(**over: object) -> SafeguardBinding:
    base: dict[str, object] = {
        "safeguard": _SG,
        "selector": Selector(context={"repo": "checkout"}),
    }
    base.update(over)
    return SafeguardBinding(**base)  # type: ignore[arg-type]


def test_matches_when_context_and_action_both_hold() -> None:
    binding = _binding(action="write-tests")
    assert binding.matches("write-tests", Context(repo="checkout")) is True


def test_context_miss_does_not_match() -> None:
    binding = _binding(action="*")
    assert binding.matches("write-tests", Context(repo="billing")) is False


def test_action_glob_scopes_the_binding() -> None:
    binding = _binding(action="write-*")
    ctx = Context(repo="checkout")
    assert binding.matches("write-tests", ctx) is True
    assert binding.matches("write-code", ctx) is True
    assert binding.matches("deploy", ctx) is False


def test_default_action_glob_governs_every_action() -> None:
    binding = _binding()  # action defaults to "*"
    ctx = Context(repo="checkout")
    assert binding.matches("write-tests", ctx) is True
    assert binding.matches("deploy", ctx) is True


def test_wildcard_context_value_requires_presence() -> None:
    # team=* means "has a team, any value" — absent dimension fails.
    binding = _binding(selector=Selector(context={"team": "*"}))
    assert binding.matches("x", Context(team="core")) is True
    assert binding.matches("x", Context(repo="checkout")) is False


def test_event_attributes_on_the_selector_are_ignored_at_governance_time() -> None:
    # A selector may carry tool/path fields; a binding delimits a region of context, so those
    # play no part — only the context predicate does.
    binding = _binding(selector=Selector(tool="Edit", path="**/*.ts", context={"repo": "checkout"}))
    assert binding.matches("write-tests", Context(repo="checkout")) is True


def test_specificity_counts_context_and_a_concrete_action() -> None:
    assert _binding(action="*").specificity == 1  # one context constraint
    assert _binding(action="write-tests").specificity == 2  # + a concrete action


def test_round_trips_through_json() -> None:
    binding = _binding(action="write-tests", priority=3)
    assert SafeguardBinding.from_json(binding.to_json()) == binding


def test_round_trips_through_dict() -> None:
    binding = _binding(selector=Selector(context={"repo": "checkout", "team": "*"}))
    assert SafeguardBinding.from_dict(binding.to_dict()) == binding
