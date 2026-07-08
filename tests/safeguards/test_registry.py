"""The :class:`InMemoryBindingRegistry`: union of distinct safeguards, dedupe of the same one."""

from __future__ import annotations

from sailguarding.classification import Selector
from sailguarding.domain import Context
from sailguarding.safeguards import (
    BindingRegistry,
    InMemoryBindingRegistry,
    Measurement,
    Safeguard,
    SafeguardBinding,
    SafeguardKind,
)

CHECKOUT = Context(repo="checkout", environment="prod")


def _safeguard(sid: str) -> Safeguard:
    return Safeguard(
        id=sid,
        label=sid,
        metric=sid,
        kind=SafeguardKind.STRUCTURAL,
        measures=Measurement.HEALTH,
    )


def _binding(
    sid: str, *, context: dict[str, str], activity: str = "*", priority: int = 0
) -> SafeguardBinding:
    return SafeguardBinding(
        safeguard=_safeguard(sid),
        selector=Selector(context=context),
        activity=activity,
        priority=priority,
    )


def test_in_memory_registry_satisfies_the_protocol() -> None:
    assert isinstance(InMemoryBindingRegistry(), BindingRegistry)


def test_resolves_the_union_of_distinct_matching_safeguards() -> None:
    registry = InMemoryBindingRegistry(
        [
            _binding("impact", context={"repo": "checkout"}),
            _binding("no-flaky-tests", context={"repo": "checkout"}),
            _binding("no-secrets", context={"repo": "billing"}),  # different region
        ]
    )
    resolved = registry.resolve("write-tests", CHECKOUT)
    assert {b.safeguard.id for b in resolved} == {"impact", "no-flaky-tests"}


def test_non_matching_context_governs_nothing() -> None:
    registry = InMemoryBindingRegistry([_binding("impact", context={"repo": "checkout"})])
    assert registry.resolve("write-tests", Context(repo="billing")) == []


def test_action_scoped_binding_only_governs_its_action() -> None:
    registry = InMemoryBindingRegistry(
        [
            _binding("impact", context={"repo": "checkout"}, activity="write-tests"),
            _binding("no-flaky-tests", context={"repo": "checkout"}),  # every activity
        ]
    )
    tests = {b.safeguard.id for b in registry.resolve("write-tests", CHECKOUT)}
    deploy = {b.safeguard.id for b in registry.resolve("deploy", CHECKOUT)}
    assert tests == {"impact", "no-flaky-tests"}
    assert deploy == {"no-flaky-tests"}  # impact is scoped to write-tests only


def test_same_safeguard_bound_twice_dedupes_to_most_specific() -> None:
    broad = _binding("impact", context={"repo": "checkout"})
    narrow = _binding("impact", context={"repo": "checkout", "environment": "prod"})
    registry = InMemoryBindingRegistry([broad, narrow])

    resolved = registry.resolve("write-tests", CHECKOUT)
    assert len(resolved) == 1  # counted once, not twice
    assert resolved[0] is narrow  # the more specific binding wins


def test_specificity_tie_breaks_by_priority() -> None:
    low = _binding("impact", context={"repo": "checkout"}, priority=0)
    high = _binding("impact", context={"repo": "checkout"}, priority=5)
    registry = InMemoryBindingRegistry([low, high])

    resolved = registry.resolve("write-tests", CHECKOUT)
    assert len(resolved) == 1
    assert resolved[0] is high


def test_exact_tie_keeps_first_registered_deterministically() -> None:
    first = _binding("impact", context={"repo": "checkout"})
    second = _binding("impact", context={"repo": "checkout"})
    registry = InMemoryBindingRegistry([first, second])

    resolved = registry.resolve("write-tests", CHECKOUT)
    assert len(resolved) == 1
    assert resolved[0] is first


def test_resolution_order_is_stable_first_appearance() -> None:
    registry = InMemoryBindingRegistry(
        [
            _binding("impact", context={"repo": "checkout"}),
            _binding("no-flaky-tests", context={"repo": "checkout"}),
        ]
    )
    resolved = registry.resolve("write-tests", CHECKOUT)
    assert [b.safeguard.id for b in resolved] == ["impact", "no-flaky-tests"]


def test_register_adds_a_binding() -> None:
    registry = InMemoryBindingRegistry()
    registry.register(_binding("impact", context={"repo": "checkout"}))
    assert len(registry.bindings) == 1
    assert registry.resolve("write-tests", CHECKOUT)[0].safeguard.id == "impact"
