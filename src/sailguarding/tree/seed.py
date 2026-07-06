"""Seeding the tree bottom-up from triaged events.

The SPEC is emphatic: **curate, don't author from a blank page.** The taxonomy grows from what
agents actually did, not from a tree invented up front. Task 04 already routes every event that
matched no action into the triage queue; this module is the path from one such
:class:`~sailguarding.classification.TriageEntry` to a **named action + a selector that recognises
it**, ready to graft into the tree (:meth:`~sailguarding.tree.ActionTree.graft`).

The selector we synthesise is the honest, literal one the event implies: its tool, the file path it
touched *or* the command it ran, and the context dimensions it carried. That is a starting point a
human refines (widen the path glob, drop a dimension), not a final rule — but it means naming a new
action produces a working classifier for the very events that prompted it, closing the observe →
classify → *model the gap* → classify-more loop.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sailguarding.classification import Selector, SelectorRule, TriageEntry
from sailguarding.domain import Action, EventRecord

# tool_input keys a touched file path may live under, mirroring the selector's own path resolution
# so a synthesised selector matches the same events the classifier would read a path from.
_PATH_KEYS = ("file_path", "path", "notebook_path")


@dataclass(frozen=True)
class SeededAction:
    """The output of naming a triaged event: a new node plus the rule that recognises it.

    :param action: The new :class:`Action`, ready to graft under a parent in the tree.
    :param rule: A :class:`~sailguarding.classification.SelectorRule` mapping the triaged event (and
        others like it) to ``action``, so the classifier resolves them next time instead of
        re-triaging.
    """

    action: Action
    rule: SelectorRule


def selector_for_event(event: EventRecord) -> Selector:
    """The literal selector implied by ``event``: its tool, its path *or* command, and its context.

    Reads a path from the first of ``file_path``/``path``/``notebook_path`` present (matching the
    classifier's own resolution); if the event carries a shell command instead, keys on that. Every
    context dimension the event ran in is pinned to its exact value — the narrowest honest selector,
    which a human then widens.
    """
    path = _event_path(event)
    command = None if path is not None else _event_command(event)
    context = {key: str(value) for key, value in event.context.items()}
    return Selector(
        tool=event.tool_name,
        path=path,
        command=command,
        context=context,
    )


def seed_action(
    entry: TriageEntry,
    *,
    action_id: str,
    label: str,
    parent_id: str | None = None,
    priority: int = 0,
) -> SeededAction:
    """Turn one triaged event into a named :class:`Action` plus the rule that recognises it.

    :param entry: The unresolved event a human is now naming.
    :param action_id: The id for the new action (unique within the tree).
    :param label: Human-readable description of the new action.
    :param parent_id: The action to graft under; ``None`` seeds a root.
    :param priority: Tie-break priority for the synthesised rule (see
        :class:`~sailguarding.classification.SelectorRule`).
    """
    action = Action(id=action_id, label=label, parent_id=parent_id)
    rule = SelectorRule(
        selector=selector_for_event(entry.event),
        action_id=action_id,
        priority=priority,
    )
    return SeededAction(action=action, rule=rule)


def seeded_rules(seeds: Iterable[SeededAction]) -> tuple[SelectorRule, ...]:
    """The selector rules from a batch of seeds, ready to feed the classifier strategy."""
    return tuple(seed.rule for seed in seeds)


def _event_path(event: EventRecord) -> str | None:
    for key in _PATH_KEYS:
        value = event.tool_input.get(key)
        if isinstance(value, str):
            return value
    return None


def _event_command(event: EventRecord) -> str | None:
    value = event.tool_input.get("command")
    return value if isinstance(value, str) else None
