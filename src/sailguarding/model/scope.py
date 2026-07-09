"""The :class:`ContextScope` — the region of context an :class:`ActivityModel` applies to.

A governance model does not apply everywhere. "Product Software Engineering" governs a handful of
product repos; "Platform Software Engineering" governs the infra ones; "Sales" governs the sales
team. A :class:`ContextScope` makes that boundary explicit and machine-readable, so a reader (and,
later, the classifier) can tell *which* model governs a given :class:`~sailguarding.domain.Context`.

It is deliberately simpler and friendlier than the classification
:class:`~sailguarding.classification.Selector`: a scope is an ordered list of
:class:`DimensionConstraint`\\ s, each naming a dimension and the **set of values it allows** — read
as ``repo ∈ {checkout, billing}``. That "one dimension, a list of options" shape is what an editor
renders as a labelled row of value chips, which is exactly how a person thinks about "where does
this model apply".

The matching rules are intentionally forgiving toward *breadth*:

- An **empty scope** (no constraints) matches every context — the model "applies everywhere".
- A constraint with **empty ``values``** matches any context that merely *has* the dimension —
  ``repo=*`` in selector terms ("has a repo, any value").
- Otherwise the context must carry the dimension and its value must be one of the allowed options.

Like every other on-disk shape in the engine, :class:`ContextScope` is **versioned, serialisable,
round-trip stable** (``ContextScope.from_dict(s.to_dict()) == s``) and **domain-agnostic** — the
same record scopes a model to ``repo ∈ {checkout}`` or to ``room ∈ {living, kitchen}``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from sailguarding.domain.context import DimensionValue

# Bumped whenever the serialised shape of a ContextScope changes, so a reader can tell which schema
# produced a stored record.
SCOPE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class DimensionConstraint:
    """One dimension of a :class:`ContextScope`: a name and the values it allows.

    :param name: The context dimension this constrains (e.g. ``"repo"``, ``"team"``).
    :param values: The allowed values, as strings. An **empty** tuple means "any value, as long as
        the dimension is present" (the ``repo=*`` case).
    """

    name: str
    values: tuple[str, ...] = ()

    def allows(self, value: DimensionValue) -> bool:
        """True when ``value`` satisfies this constraint (empty ``values`` allows anything)."""
        return not self.values or str(value) in self.values

    def describe(self) -> str:
        """A human phrase: ``repo = checkout`` / ``repo ∈ {a, b}`` / bare ``repo``."""
        if not self.values:
            return self.name
        if len(self.values) == 1:
            return f"{self.name} = {self.values[0]}"
        return f"{self.name} ∈ {{{', '.join(self.values)}}}"

    def to_dict(self) -> dict[str, Any]:
        """A JSON-compatible dict."""
        return {"name": self.name, "values": list(self.values)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DimensionConstraint:
        """Rebuild a constraint from :meth:`to_dict` output."""
        return cls(name=data["name"], values=tuple(data.get("values", ())))


@dataclass(frozen=True)
class ContextScope:
    """The region of context a model applies to — an ordered list of dimension constraints.

    Every transform is pure and value-returning: :meth:`set_dimension` and :meth:`remove_dimension`
    each return a *new* scope and never mutate the receiver, matching the aggregate style used
    everywhere else in the engine.

    :param dimensions: The constraints, in author order. An empty tuple matches every context.
    :param schema_version: The record schema version; defaults to the current one.
    """

    dimensions: tuple[DimensionConstraint, ...] = ()
    schema_version: int = field(default=SCOPE_SCHEMA_VERSION)

    @classmethod
    def empty(cls) -> ContextScope:
        """The everywhere scope: no constraints, so it matches every context."""
        return cls()

    # -- queries ------------------------------------------------------------------------------

    def matches(self, context: Mapping[str, DimensionValue]) -> bool:
        """True when every constraint holds for ``context`` (an empty scope matches everything)."""
        for constraint in self.dimensions:
            if constraint.name not in context:
                return False
            if not constraint.allows(context[constraint.name]):
                return False
        return True

    def describe(self) -> str:
        """A human summary, e.g. ``repo ∈ {checkout, billing}; environment = staging``.

        Returns ``"applies everywhere"`` when there are no constraints — the honest reading of an
        empty scope.
        """
        if not self.dimensions:
            return "applies everywhere"
        return "; ".join(c.describe() for c in self.dimensions)

    # -- transforms ---------------------------------------------------------------------------

    def set_dimension(self, name: str, values: Iterable[str]) -> ContextScope:
        """A new scope with ``name`` constrained to ``values`` (replacing any existing constraint).

        The constraint keeps its position if ``name`` was already present, otherwise it is appended,
        so editing an existing dimension does not reshuffle the list. Duplicate values are dropped,
        author order preserved.
        """
        deduped = tuple(dict.fromkeys(str(v) for v in values))
        constraint = DimensionConstraint(name=name, values=deduped)
        if any(c.name == name for c in self.dimensions):
            updated = tuple(constraint if c.name == name else c for c in self.dimensions)
        else:
            updated = (*self.dimensions, constraint)
        return ContextScope(dimensions=updated, schema_version=self.schema_version)

    def remove_dimension(self, name: str) -> ContextScope:
        """A new scope with the ``name`` constraint dropped (a no-op if it was not present)."""
        updated = tuple(c for c in self.dimensions if c.name != name)
        return ContextScope(dimensions=updated, schema_version=self.schema_version)

    # -- serialisation ------------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """A JSON-compatible dict; constraints keep author order."""
        return {
            "schema_version": self.schema_version,
            "dimensions": [c.to_dict() for c in self.dimensions],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ContextScope:
        """Rebuild a scope from :meth:`to_dict` output, rejecting an unknown schema version."""
        version = data.get("schema_version", SCOPE_SCHEMA_VERSION)
        if version != SCOPE_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported ContextScope schema_version {version!r}; "
                f"this build reads version {SCOPE_SCHEMA_VERSION}"
            )
        return cls(
            dimensions=tuple(DimensionConstraint.from_dict(c) for c in data.get("dimensions", ())),
            schema_version=version,
        )
