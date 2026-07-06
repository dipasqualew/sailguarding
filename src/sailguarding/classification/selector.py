"""The declarative selector language: predicates over ``(event attributes, context)``.

An **action is defined by a selector** — a serialisable predicate that must be true of both
sides of an event at once: the tool attributes (tool name, the file path it touched, the shell
command it ran) *and* the context labels it ran in (``repo=checkout``, ``team=*``). Both sides
live in one :class:`Selector`; that single-object requirement is what lets safeguards (task 05+)
bind to the same selectors classification uses.

Two glob dialects are used deliberately:

- **Paths** use ``**``-aware glob semantics (``*`` stays within a path segment, ``**`` spans
  segments) so ``**/*.test.ts`` matches ``foo.test.ts`` and ``src/a/b.test.ts`` alike.
- **Tool names, commands, and context values** use flat, case-sensitive :func:`fnmatch.fnmatchcase`
  globbing — there are no path segments to respect there.

**The known v1 weakness, on purpose:** a shell command that writes code
(``Bash(echo ... > hello.py)``) is matched as a *command*, not as a path edit, so a path-glob
selector slips it. That is the honest floor a later model strategy has to beat; it is recorded
here rather than hidden.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from functools import cache
from typing import Any

from sailguarding.domain import EventRecord

# tool_input keys the sensor may carry a touched file path under, in priority order. The
# selector reads a path attribute from the first one present.
_PATH_KEYS = ("file_path", "path", "notebook_path")
# The wildcards that match anything and therefore add nothing to a selector's specificity.
_UNIVERSAL = frozenset({"*", "**"})


@dataclass(frozen=True)
class Selector:
    """A declarative predicate over one event and its context.

    Every field is optional; an unset field imposes no constraint. A selector matches an event
    only when *all* of its set fields match. ``context`` maps a dimension name to a value glob;
    the dimension must be present on the event (``team=*`` means "has a team, any value").

    :param tool: Glob matched against ``tool_name`` (e.g. ``"Edit"``, ``"Bash"``, ``"*"``).
    :param path: ``**``-aware glob matched against the event's touched file path.
    :param command: Glob matched against the event's shell command.
    :param context: Dimension name → value glob; each named dimension must be present and match.
    """

    tool: str | None = None
    path: str | None = None
    command: str | None = None
    context: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Copy the mapping so a later mutation of the caller's dict can't change this selector.
        object.__setattr__(self, "context", dict(self.context))

    def matches(self, event: EventRecord) -> bool:
        """True when every set field of this selector holds for ``event``."""
        if self.tool is not None and not fnmatchcase(event.tool_name, self.tool):
            return False

        if self.path is not None:
            path = _event_path(event)
            if path is None or not _path_matches(path, self.path):
                return False

        if self.command is not None:
            command = _event_command(event)
            if command is None or not fnmatchcase(command, self.command):
                return False

        return self.matches_context(event.context)

    def matches_context(self, context: Mapping[str, Any]) -> bool:
        """True when this selector's context predicate holds for ``context`` alone.

        The context half of :meth:`matches`, split out so a caller with no event — a safeguard
        binding resolving over an ``(action, context)`` (task 06) — can evaluate the *same*
        predicate language against a bare :class:`~sailguarding.domain.Context`. Each named
        dimension must be present and its value glob-match; a selector that names no context
        dimensions matches every context. The event-attribute fields (``tool``/``path``/
        ``command``) play no part here — they describe how an *event* is recognised, not how a
        region of context is delimited.
        """
        for dimension, pattern in self.context.items():
            actual = context.get(dimension)
            if actual is None or not fnmatchcase(str(actual), pattern):
                return False
        return True

    @property
    def specificity(self) -> int:
        """How many constraints this selector actually narrows on.

        Higher = more specific. A bare universal wildcard (``*``/``**``) constrains matching but
        narrows nothing, so it scores 0; ``team=checkout`` scores 1. The matcher uses this to
        resolve overlaps: the most-specific selector wins (see :mod:`.matcher`).
        """
        attrs = (self.tool, self.path, self.command)
        score = sum(1 for value in attrs if value is not None and value not in _UNIVERSAL)
        score += sum(1 for pattern in self.context.values() if pattern not in _UNIVERSAL)
        return score

    def to_dict(self) -> dict[str, Any]:
        """A JSON-serialisable form. Unset fields are omitted so the record stays declarative."""
        data: dict[str, Any] = {}
        if self.tool is not None:
            data["tool"] = self.tool
        if self.path is not None:
            data["path"] = self.path
        if self.command is not None:
            data["command"] = self.command
        if self.context:
            data["context"] = dict(self.context)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Selector:
        """Rebuild a selector from :meth:`to_dict` output."""
        return cls(
            tool=data.get("tool"),
            path=data.get("path"),
            command=data.get("command"),
            context=data.get("context", {}),
        )


@dataclass(frozen=True)
class SelectorRule:
    """A selector bound to the action it recognises, with a tie-break priority.

    :param selector: The predicate to evaluate.
    :param action_id: The action an event resolves to when this rule wins.
    :param priority: Breaks ties between equally specific selectors (higher wins). Defaults to 0.
    """

    selector: Selector
    action_id: str
    priority: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "selector": self.selector.to_dict(),
            "action_id": self.action_id,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SelectorRule:
        return cls(
            selector=Selector.from_dict(data["selector"]),
            action_id=data["action_id"],
            priority=data.get("priority", 0),
        )


def _event_path(event: EventRecord) -> str | None:
    """The touched file path from the event's tool input, or ``None`` if it carries none."""
    for key in _PATH_KEYS:
        value = event.tool_input.get(key)
        if isinstance(value, str):
            return value
    return None


def _event_command(event: EventRecord) -> str | None:
    """The shell command from the event's tool input, or ``None`` if it carries none."""
    value = event.tool_input.get("command")
    return value if isinstance(value, str) else None


def _path_matches(path: str, pattern: str) -> bool:
    return _compile_path_glob(pattern).match(path) is not None


@cache
def _compile_path_glob(pattern: str) -> re.Pattern[str]:
    """Compile a ``**``-aware path glob to an anchored regex.

    ``*`` matches any run of non-``/`` characters, ``?`` a single non-``/`` character, and ``**``
    spans path segments — ``**/`` also collapses to zero leading directories, so ``**/x`` matches
    a bare ``x``. Everything else is a literal.
    """
    out = ["(?s:"]
    i, n = 0, len(pattern)
    while i < n:
        char = pattern[i]
        if char == "*":
            j = i
            while j < n and pattern[j] == "*":
                j += 1
            if j - i >= 2:  # '**' (or more) — span segments
                if j < n and pattern[j] == "/":
                    out.append("(?:.*/)?")  # allow zero leading directories
                    j += 1
                else:
                    out.append(".*")
                i = j
            else:
                out.append("[^/]*")
                i += 1
        elif char == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(char))
            i += 1
    out.append(r")\Z")
    return re.compile("".join(out))
