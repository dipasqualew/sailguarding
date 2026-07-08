"""Seeding the tree bottom-up from triaged events.

The SPEC is emphatic: **curate, don't author from a blank page.** The taxonomy grows from what
agents actually did, not from a tree invented up front. Task 04 already routes every event that
matched no activity into the triage queue; this module is the path from one such
:class:`~sailguarding.classification.TriageEntry` to a **named activity + a selector that recognises
it**, ready to graft into the tree (:meth:`~sailguarding.tree.ActivityTree.graft`).

The selector we synthesise is the honest, literal one the event implies: its tool, the file path it
touched *or* the command it ran, and the context dimensions it carried. That is a starting point a
human refines (widen the path glob, drop a dimension), not a final rule — but it means naming a new
activity produces a working classifier for the very events that prompted it, closing the observe →
classify → *model the gap* → classify-more loop.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sailguarding.classification import Selector, SelectorRule, TriageEntry
from sailguarding.domain import Activity, EventRecord

# tool_input keys a touched file path may live under, mirroring the selector's own path resolution
# so a synthesised selector matches the same events the classifier would read a path from.
_PATH_KEYS = ("file_path", "path", "notebook_path")


@dataclass(frozen=True)
class SeededActivity:
    """The output of naming a triaged event: a new node plus the rule that recognises it.

    :param activity: The new :class:`Activity`, ready to graft under a parent in the tree.
    :param rule: A :class:`~sailguarding.classification.SelectorRule` mapping the triaged event (and
        others like it) to ``activity``, so the classifier resolves them next time instead of
        re-triaging.
    """

    activity: Activity
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


def seed_activity(
    entry: TriageEntry,
    *,
    activity_id: str,
    label: str,
    parent_id: str | None = None,
    priority: int = 0,
) -> SeededActivity:
    """Turn one triaged event into a named :class:`Activity` plus the rule that recognises it.

    :param entry: The unresolved event a human is now naming.
    :param activity_id: The id for the new activity (unique within the tree).
    :param label: Human-readable description of the new activity.
    :param parent_id: The activity to graft under; ``None`` seeds a root.
    :param priority: Tie-break priority for the synthesised rule (see
        :class:`~sailguarding.classification.SelectorRule`).
    """
    activity = Activity(id=activity_id, label=label, parent_id=parent_id)
    rule = SelectorRule(
        selector=selector_for_event(entry.event),
        activity_id=activity_id,
        priority=priority,
    )
    return SeededActivity(activity=activity, rule=rule)


def seeded_rules(seeds: Iterable[SeededActivity]) -> tuple[SelectorRule, ...]:
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
