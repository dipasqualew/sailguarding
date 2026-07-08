"""Binding a safeguard to the region of work it governs.

A :class:`Safeguard` says *what* must hold; a :class:`SafeguardBinding` says *where* — which
``(activity, context)`` region it governs. It binds through the same :class:`Selector` language
classification uses (task 04), reused verbatim: the SPEC's "No flaky tests, ``team=*,
repo=checkout``" is a safeguard bound to a region of context. Binding through the shared selector
is deliberate — if the predicate language ever grows (e.g. sequences, open question #3), safeguards
inherit the change for free instead of drifting a second dialect.

A binding narrows on two independent axes:

- **Context**, via the selector's context predicate (:meth:`Selector.matches_context`). Only the
  context half of the selector participates — a binding delimits a *region of context*, not an
  event, so ``tool``/``path``/``command`` fields (if any) are ignored at governance time.
- **Activity**, via an ``activity`` id-glob. ``"*"`` (the default) governs every activity in the
  region; a concrete id (``"write-tests"``) or a glob (``"write-*"``) scopes the safeguard to
  particular activities.

Both must hold for the binding to govern an ``(activity, context)``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import Any

from sailguarding.classification import Selector
from sailguarding.safeguards.safeguard import Safeguard


@dataclass(frozen=True)
class SafeguardBinding:
    """A :class:`Safeguard` bound to the ``(activity, context)`` region it governs.

    :param safeguard: The governed safeguard.
    :param selector: The context predicate delimiting the region; its context dimensions must match
        the resolved context. Event-attribute fields are not evaluated here (see the module
        docstring).
    :param activity: An activity-id glob (default ``"*"``, every activity). A binding governs an
        activity only when this glob matches the activity's id.
    :param priority: Breaks ties between equally specific bindings *of the same safeguard* when the
        registry dedupes an overlap (higher wins). Mirrors :class:`SelectorRule.priority`.
    """

    safeguard: Safeguard
    selector: Selector = field(default_factory=Selector)
    activity: str = "*"
    priority: int = 0

    def matches(self, activity_id: str, context: Mapping[str, Any]) -> bool:
        """True when this binding governs ``activity_id`` running in ``context``.

        Both axes must hold: the ``activity`` glob matches ``activity_id`` and the selector's
        context predicate matches ``context``.
        """
        return fnmatchcase(activity_id, self.activity) and self.selector.matches_context(context)

    @property
    def specificity(self) -> int:
        """How many axes this binding actually narrows on — the overlap tie-breaker.

        The selector's own :attr:`~Selector.specificity` (context constraints that narrow) plus one
        if the ``activity`` glob is not the bare ``"*"`` wildcard. A more specific binding wins when
        two bindings of the *same* safeguard both match (see :mod:`.registry`), mirroring the
        classifier's specificity handling.
        """
        return self.selector.specificity + (0 if self.activity == "*" else 1)

    def to_dict(self) -> dict[str, Any]:
        """A JSON-serialisable form; the selector serialises through its own :meth:`to_dict`."""
        return {
            "safeguard": self.safeguard.to_dict(),
            "selector": self.selector.to_dict(),
            "activity": self.activity,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SafeguardBinding:
        """Rebuild a binding from :meth:`to_dict` output."""
        return cls(
            safeguard=Safeguard.from_dict(data["safeguard"]),
            selector=Selector.from_dict(data.get("selector", {})),
            activity=data.get("activity", "*"),
            priority=data.get("priority", 0),
        )

    def to_json(self) -> str:
        """Serialise to a canonical, single-line JSON string (sorted keys, tight separators)."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> SafeguardBinding:
        """Parse a binding from a JSON string produced by :meth:`to_json`."""
        return cls.from_dict(json.loads(text))
