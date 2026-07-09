"""The :class:`Workspace` — a navigable collection of :class:`ActivityModel`\\ s.

A single :class:`~sailguarding.model.model.ActivityModel` governs one region of work. A real
organisation runs several that do not overlap, or only partly: a "Sales" model, a "Product Software
Engineering" model, a "Platform Software Engineering" model. The :class:`Workspace` is the container
that holds them, tracks which one is **active** (the one the editor is currently showing), and moves
activities/risks/safeguards **between** them by copying — never by reference, so importing into one
model leaves the source untouched.

It mirrors the conventions of :class:`ActivityModel` exactly: a frozen value object whose every
transform is **pure and value-returning** (a new :class:`Workspace`, never a mutation), the whole
thing **versioned, serialisable, and round-trip stable**
(``Workspace.from_json(w.to_json()) == w``). Model identity lives on the model
(:attr:`ActivityModel.id`); the workspace only orders them and remembers the active one.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from sailguarding.model.model import ActivityModel, _unique_id

# Bumped whenever the serialised shape of a Workspace changes, so a reader can tell which schema
# produced a stored record.
WORKSPACE_SCHEMA_VERSION = 1

# The kinds of library entity that can be imported from one model into another.
ImportKind = Literal["activity", "risk", "safeguard"]


@dataclass(frozen=True)
class Workspace:
    """An ordered collection of :class:`ActivityModel`\\ s with a remembered active model.

    :param models: The models, in display order. Each carries its own :attr:`ActivityModel.id`.
    :param active_id: The id of the model the editor is showing, or ``None`` when empty.
    :param schema_version: The record schema version; defaults to the current one.
    """

    models: tuple[ActivityModel, ...] = ()
    active_id: str | None = None
    schema_version: int = field(default=WORKSPACE_SCHEMA_VERSION)

    # -- construction -------------------------------------------------------------------------

    @classmethod
    def empty(cls) -> Workspace:
        """An empty workspace: no models, nothing active."""
        return cls()

    @classmethod
    def of(cls, *models: ActivityModel) -> Workspace:
        """A workspace holding ``models`` in order, with the first one active."""
        return cls(models=tuple(models), active_id=models[0].id if models else None)

    # -- queries ------------------------------------------------------------------------------

    def find(self, model_id: str) -> ActivityModel | None:
        """The model with ``model_id``, or ``None``."""
        for model in self.models:
            if model.id == model_id:
                return model
        return None

    def active(self) -> ActivityModel | None:
        """The active model, or ``None`` if the workspace is empty / nothing is selected."""
        return self.find(self.active_id) if self.active_id is not None else None

    def model_ids(self) -> tuple[str, ...]:
        """The model ids, in display order."""
        return tuple(model.id for model in self.models)

    # -- model transforms ---------------------------------------------------------------------

    def add_model(self, name: str) -> tuple[Workspace, str]:
        """A new workspace with a fresh, empty model appended and made active; returns it, id."""
        new_id = _unique_id(name, set(self.model_ids()), fallback="model")
        model = ActivityModel.empty(model_id=new_id, name=name)
        return self._with(models=(*self.models, model), active_id=new_id), new_id

    def rename_model(self, model_id: str, name: str) -> Workspace:
        """A new workspace with ``model_id``'s name set. Raises :class:`KeyError` if unknown."""
        return self.replace_model(self._require(model_id).set_name(name))

    def remove_model(self, model_id: str) -> Workspace:
        """A new workspace with ``model_id`` removed; the active model falls back to the first left.

        Raises :class:`KeyError` if the model is unknown.
        """
        self._require(model_id)
        remaining = tuple(m for m in self.models if m.id != model_id)
        active = self.active_id
        if active == model_id:
            active = remaining[0].id if remaining else None
        return self._with(models=remaining, active_id=active)

    def select(self, model_id: str) -> Workspace:
        """A new workspace with ``model_id`` active. Raises :class:`KeyError` if unknown."""
        self._require(model_id)
        return self._with(active_id=model_id)

    def replace_model(self, model: ActivityModel) -> Workspace:
        """A new workspace with the model whose id is ``model.id`` swapped for ``model``.

        This is how an edit to the active model lands: the caller applies an
        :class:`ActivityModel` transform, then replaces the old model by id. Raises
        :class:`KeyError` if no model with that id is present.
        """
        self._require(model.id)
        models = tuple(model if m.id == model.id else m for m in self.models)
        return self._with(models=models)

    # -- cross-model import -------------------------------------------------------------------

    def import_into(
        self,
        target_id: str,
        source_id: str,
        kind: ImportKind,
        entity_id: str,
        parent_id: str | None = None,
    ) -> tuple[Workspace, str]:
        """Copy ``entity_id`` (an activity/risk/safeguard) from ``source_id`` into ``target_id``.

        The copy leaves the source model untouched (every :class:`ActivityModel` import is
        value-returning). Returns the new workspace and the imported entity's id in the target.
        Raises :class:`KeyError` for an unknown model or entity, :class:`ValueError` for an unknown
        ``kind``.
        """
        target = self._require(target_id)
        source = self._require(source_id)
        if kind == "activity":
            updated, new_id = target.import_activity(source, entity_id, parent_id)
        elif kind == "risk":
            risk = source.find_risk(entity_id)
            if risk is None:
                raise KeyError(f"no risk {entity_id!r} in source model {source_id!r}")
            updated, new_id = target.import_risk(risk)
        elif kind == "safeguard":
            safeguard = source.find_safeguard(entity_id)
            if safeguard is None:
                raise KeyError(f"no safeguard {entity_id!r} in source model {source_id!r}")
            updated, new_id = target.import_safeguard(safeguard)
        else:
            raise ValueError(f"unknown import kind {kind!r}")
        return self.replace_model(updated), new_id

    # -- serialisation ------------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """A JSON-compatible dict; models keep display order."""
        return {
            "schema_version": self.schema_version,
            "active_id": self.active_id,
            "models": [m.to_dict() for m in self.models],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Workspace:
        """Rebuild a workspace from :meth:`to_dict` output, rejecting an unknown schema version."""
        version = data.get("schema_version", WORKSPACE_SCHEMA_VERSION)
        if version != WORKSPACE_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported Workspace schema_version {version!r}; "
                f"this build reads version {WORKSPACE_SCHEMA_VERSION}"
            )
        return cls(
            models=tuple(ActivityModel.from_dict(m) for m in data.get("models", ())),
            active_id=data.get("active_id"),
            schema_version=version,
        )

    def to_json(self) -> str:
        """Serialise to a canonical, single-line JSON string (sorted keys, tight separators)."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> Workspace:
        """Parse a workspace from a JSON string produced by :meth:`to_json`."""
        return cls.from_dict(json.loads(text))

    # -- internals ----------------------------------------------------------------------------

    def _with(self, **changes: Any) -> Workspace:
        """A copy with ``changes`` applied — the value-returning primitive every transform uses."""
        return Workspace(
            models=changes.get("models", self.models),
            active_id=changes.get("active_id", self.active_id),
            schema_version=self.schema_version,
        )

    def _require(self, model_id: str) -> ActivityModel:
        model = self.find(model_id)
        if model is None:
            raise KeyError(f"no model {model_id!r} in workspace")
        return model
