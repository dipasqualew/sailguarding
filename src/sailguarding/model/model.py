"""The :class:`ActivityModel` — the persistable governance aggregate.

An :class:`~sailguarding.domain.Activity` is deliberately a *bare* tree node: an id, a label, a
parent, children. It carries no governance. This module is where the governance lives, as a single
frozen value object that ties four things together:

- the **activity tree** (:class:`~sailguarding.tree.ActivityTree`) — the work being modelled;
- a reusable **risk library** (:class:`~sailguarding.model.risk.Risk`) — hazards named once and
  referenced many times;
- a reusable **safeguard library** (:class:`~sailguarding.safeguards.Safeguard`) — controls named
  once and reused across activities and risks;
- and the **edges** between them: which risks an activity faces, and which safeguard mitigates which
  risk on which activity.

The edges live *here*, on the aggregate, not on :class:`Activity`. Keeping associations out of the
node is what lets the same "data loss" risk and the same "peer review" safeguard be shared across
many activities and counted for reuse — the node stays a pure structural unit, and the model owns
the relationships.

Every transform is **pure and value-returning**: like :meth:`ActivityTree.graft`, each method
returns a *new* :class:`ActivityModel` and never mutates the receiver. The whole aggregate is
versioned, serialisable, round-trip stable (``ActivityModel.from_json(m.to_json()) == m``), and
domain-agnostic.

**The forest, via a synthetic root.** :class:`ActivityTree` holds a single root, but a governance
model needs to hold *several* top-level activities (a forest). We reconcile the two by making the
tree's root a fixed, hidden container node — id :data:`ROOT_ID` (``"__root__"``), empty label — that
is never shown to a user. "Add a top-level activity" grafts under this synthetic root; the real
top-level activities are its children, reachable via :meth:`ActivityModel.top_level`. The synthetic
root round-trips like any other node and cannot itself be renamed away or removed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sailguarding.domain import Activity
from sailguarding.model.risk import Risk
from sailguarding.safeguards import Measurement, Safeguard, SafeguardKind
from sailguarding.tree import ActivityTree

# Bumped whenever the serialised shape of an ActivityModel changes, so a reader can tell which
# schema produced a stored record.
MODEL_SCHEMA_VERSION = 1

# The id of the fixed, hidden container node that lets a single-root ActivityTree hold a forest of
# top-level activities. Never shown to a user; grafting a "top-level" activity grafts under this.
ROOT_ID = "__root__"


@dataclass(frozen=True)
class ActivityModel:
    """The governance aggregate: a tree, its risk/safeguard libraries, and the edges between them.

    :param tree: The activity tree. Its root is the synthetic :data:`ROOT_ID` container; real
        top-level activities are its children (see :meth:`top_level`).
    :param risks: The reusable risk library — each :class:`Risk` referenced by id from the edges.
    :param safeguards: The reusable safeguard library — each :class:`Safeguard` referenced by id.
    :param activity_risks: ``(activity_id, risk_id)`` edges: which risks each activity faces.
    :param mitigations: ``(activity_id, risk_id, safeguard_id)`` edges: an explicit "this safeguard
        mitigates that risk on that activity".
    :param schema_version: The record schema version; defaults to the current one.
    """

    tree: ActivityTree
    risks: tuple[Risk, ...] = ()
    safeguards: tuple[Safeguard, ...] = ()
    activity_risks: frozenset[tuple[str, str]] = frozenset()
    mitigations: frozenset[tuple[str, str, str]] = frozenset()
    schema_version: int = field(default=MODEL_SCHEMA_VERSION)

    # -- construction -------------------------------------------------------------------------

    @classmethod
    def empty(cls) -> ActivityModel:
        """An empty model: just the synthetic root, no activities, risks, safeguards, or edges."""
        return cls(tree=ActivityTree(Activity(id=ROOT_ID, label="")))

    # -- queries ------------------------------------------------------------------------------

    def top_level(self) -> tuple[Activity, ...]:
        """The real top-level activities — the children of the synthetic :data:`ROOT_ID` root."""
        root = self.tree.find(ROOT_ID)
        return root.children if root is not None else ()

    def find_risk(self, risk_id: str) -> Risk | None:
        """The risk with ``risk_id`` in the library, or ``None``."""
        for risk in self.risks:
            if risk.id == risk_id:
                return risk
        return None

    def find_safeguard(self, safeguard_id: str) -> Safeguard | None:
        """The safeguard with ``safeguard_id`` in the library, or ``None``."""
        for safeguard in self.safeguards:
            if safeguard.id == safeguard_id:
                return safeguard
        return None

    def risks_for(self, activity_id: str) -> tuple[Risk, ...]:
        """The risks ``activity_id`` faces, in library order."""
        faced = {rid for (aid, rid) in self.activity_risks if aid == activity_id}
        return tuple(risk for risk in self.risks if risk.id in faced)

    def safeguards_for(self, activity_id: str, risk_id: str) -> tuple[Safeguard, ...]:
        """The safeguards mitigating ``risk_id`` on ``activity_id``, in library order."""
        mitigating = {
            sid for (aid, rid, sid) in self.mitigations if aid == activity_id and rid == risk_id
        }
        return tuple(sg for sg in self.safeguards if sg.id in mitigating)

    def activities_using_risk(self, risk_id: str) -> tuple[str, ...]:
        """The distinct activity ids that face ``risk_id`` (sorted) — the risk's reuse count."""
        return tuple(sorted({aid for (aid, rid) in self.activity_risks if rid == risk_id}))

    def activities_using_safeguard(self, safeguard_id: str) -> tuple[str, ...]:
        """The distinct activity ids mitigated by ``safeguard_id`` (sorted) — its reuse count."""
        return tuple(sorted({aid for (aid, _rid, sid) in self.mitigations if sid == safeguard_id}))

    # -- tree transforms ----------------------------------------------------------------------

    def add_activity(self, parent_id: str | None, label: str) -> tuple[ActivityModel, str]:
        """A new model with a fresh activity added under ``parent_id`` (``None`` = top level).

        Returns the new model *and* the generated activity id. ``parent_id=None`` adds a top-level
        activity by grafting under the synthetic :data:`ROOT_ID` root. Raises :class:`KeyError` if
        an explicit ``parent_id`` is not in the tree.
        """
        target_parent = ROOT_ID if parent_id is None else parent_id
        if self.tree.find(target_parent) is None:
            raise KeyError(f"no activity {target_parent!r} in model to add under")
        new_id = _unique_id(label, self._activity_ids(), fallback="activity")
        grown = self.tree.graft(target_parent, Activity(id=new_id, label=label))
        return self._with(tree=grown), new_id

    def rename_activity(self, activity_id: str, label: str) -> ActivityModel:
        """A new model with ``activity_id``'s label set to ``label``.

        Raises :class:`KeyError` if the activity is not in the tree.
        """
        if self.tree.find(activity_id) is None:
            raise KeyError(f"no activity {activity_id!r} in model to rename")
        renamed = ActivityTree(
            root=_rename_node(self.tree.root, activity_id, label),
            schema_version=self.tree.schema_version,
        )
        return self._with(tree=renamed)

    def remove_activity(self, activity_id: str) -> ActivityModel:
        """A new model with ``activity_id`` and its whole subtree removed, edges cascaded.

        Every ``activity_risks`` and ``mitigations`` edge whose ``activity_id`` is the removed node
        *or any descendant* is dropped. Removing the synthetic :data:`ROOT_ID` root is a no-op.
        Raises :class:`KeyError` if the activity is not in the tree.
        """
        if activity_id == ROOT_ID:
            return self
        node = self.tree.find(activity_id)
        if node is None:
            raise KeyError(f"no activity {activity_id!r} in model to remove")
        gone = {n.id for n in node.walk()}
        pruned = ActivityTree(
            root=_remove_node(self.tree.root, activity_id),
            schema_version=self.tree.schema_version,
        )
        activity_risks = frozenset(e for e in self.activity_risks if e[0] not in gone)
        mitigations = frozenset(e for e in self.mitigations if e[0] not in gone)
        return self._with(tree=pruned, activity_risks=activity_risks, mitigations=mitigations)

    # -- library transforms -------------------------------------------------------------------

    def add_risk(self, label: str, description: str = "") -> tuple[ActivityModel, str]:
        """A new model with a fresh :class:`Risk` in the library; returns the model and its id."""
        new_id = _unique_id(label, {r.id for r in self.risks}, fallback="risk")
        risk = Risk(id=new_id, label=label, description=description)
        return self._with(risks=(*self.risks, risk)), new_id

    def add_safeguard(
        self,
        label: str,
        kind: SafeguardKind,
        measures: Measurement,
        metric: str = "",
        cadence: timedelta | None = None,
    ) -> tuple[ActivityModel, str]:
        """A new model with a fresh :class:`Safeguard` in the library; returns the model and id."""
        new_id = _unique_id(label, {s.id for s in self.safeguards}, fallback="safeguard")
        safeguard = Safeguard(
            id=new_id,
            label=label,
            metric=metric,
            kind=kind,
            measures=measures,
            cadence=cadence,
        )
        return self._with(safeguards=(*self.safeguards, safeguard)), new_id

    # -- edge transforms ----------------------------------------------------------------------

    def attach_risk(self, activity_id: str, risk_id: str) -> ActivityModel:
        """A new model where ``activity_id`` faces ``risk_id``.

        Raises :class:`KeyError` if the activity or the risk is unknown.
        """
        self._require_activity(activity_id)
        self._require_risk(risk_id)
        return self._with(activity_risks=self.activity_risks | {(activity_id, risk_id)})

    def detach_risk(self, activity_id: str, risk_id: str) -> ActivityModel:
        """A new model where ``activity_id`` no longer faces ``risk_id``.

        Also drops every mitigation for that ``(activity_id, risk_id)`` pair, since a mitigation
        with no risk to mitigate is meaningless. Raises :class:`KeyError` if the activity or risk is
        unknown.
        """
        self._require_activity(activity_id)
        self._require_risk(risk_id)
        activity_risks = self.activity_risks - {(activity_id, risk_id)}
        mitigations = frozenset(
            e for e in self.mitigations if not (e[0] == activity_id and e[1] == risk_id)
        )
        return self._with(activity_risks=activity_risks, mitigations=mitigations)

    def add_mitigation(self, activity_id: str, risk_id: str, safeguard_id: str) -> ActivityModel:
        """A new model recording that ``safeguard_id`` mitigates ``risk_id`` on ``activity_id``.

        Raises :class:`KeyError` if the activity, risk, or safeguard is unknown.
        """
        self._require_activity(activity_id)
        self._require_risk(risk_id)
        self._require_safeguard(safeguard_id)
        return self._with(mitigations=self.mitigations | {(activity_id, risk_id, safeguard_id)})

    def remove_mitigation(self, activity_id: str, risk_id: str, safeguard_id: str) -> ActivityModel:
        """A new model with the ``(activity, risk, safeguard)`` mitigation edge dropped."""
        return self._with(mitigations=self.mitigations - {(activity_id, risk_id, safeguard_id)})

    # -- serialisation ------------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """A JSON-compatible dict; edge sets serialise as sorted lists of lists for canonicality."""
        return {
            "schema_version": self.schema_version,
            "tree": self.tree.to_dict(),
            "risks": [r.to_dict() for r in self.risks],
            "safeguards": [s.to_dict() for s in self.safeguards],
            "activity_risks": sorted([a, r] for (a, r) in self.activity_risks),
            "mitigations": sorted([a, r, s] for (a, r, s) in self.mitigations),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ActivityModel:
        """Rebuild a model from :meth:`to_dict` output, rejecting an unknown schema version."""
        version = data.get("schema_version", MODEL_SCHEMA_VERSION)
        if version != MODEL_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported ActivityModel schema_version {version!r}; "
                f"this build reads version {MODEL_SCHEMA_VERSION}"
            )
        return cls(
            tree=ActivityTree.from_dict(data["tree"]),
            risks=tuple(Risk.from_dict(r) for r in data.get("risks", ())),
            safeguards=tuple(Safeguard.from_dict(s) for s in data.get("safeguards", ())),
            activity_risks=frozenset((a, r) for (a, r) in data.get("activity_risks", ())),
            mitigations=frozenset((a, r, s) for (a, r, s) in data.get("mitigations", ())),
            schema_version=version,
        )

    def to_json(self) -> str:
        """Serialise to a canonical, single-line JSON string (sorted keys, tight separators)."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> ActivityModel:
        """Parse a model from a JSON string produced by :meth:`to_json`."""
        return cls.from_dict(json.loads(text))

    # -- internals ----------------------------------------------------------------------------

    def _with(self, **changes: Any) -> ActivityModel:
        """A copy with ``changes`` applied — the value-returning primitive every transform uses."""
        return ActivityModel(
            tree=changes.get("tree", self.tree),
            risks=changes.get("risks", self.risks),
            safeguards=changes.get("safeguards", self.safeguards),
            activity_risks=changes.get("activity_risks", self.activity_risks),
            mitigations=changes.get("mitigations", self.mitigations),
            schema_version=self.schema_version,
        )

    def _activity_ids(self) -> set[str]:
        return {n.id for n in self.tree.walk()}

    def _require_activity(self, activity_id: str) -> None:
        if self.tree.find(activity_id) is None:
            raise KeyError(f"no activity {activity_id!r} in model")

    def _require_risk(self, risk_id: str) -> None:
        if self.find_risk(risk_id) is None:
            raise KeyError(f"no risk {risk_id!r} in model")

    def _require_safeguard(self, safeguard_id: str) -> None:
        if self.find_safeguard(safeguard_id) is None:
            raise KeyError(f"no safeguard {safeguard_id!r} in model")


# -- id generation ----------------------------------------------------------------------------

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slugify(label: str) -> str:
    """Lowercase ``label``, turn every non-alphanumeric run into a single hyphen, trim hyphens."""
    return _NON_ALNUM.sub("-", label.lower()).strip("-")


def _unique_id(label: str, existing: Iterable[str], fallback: str) -> str:
    """A slug of ``label`` unique against ``existing``, suffixed ``-2``, ``-3``, … on collision."""
    taken = set(existing)
    base = _slugify(label) or fallback
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


# -- tree rebuilding (rename / remove; ActivityTree only grows) --------------------------------


def _rename_node(node: Activity, activity_id: str, label: str) -> Activity:
    """Rebuild ``node``'s subtree with the node whose id is ``activity_id`` given ``label``."""
    if node.id == activity_id:
        return Activity(
            id=node.id,
            label=label,
            parent_id=node.parent_id,
            children=node.children,
        )
    return Activity(
        id=node.id,
        label=node.label,
        parent_id=node.parent_id,
        children=tuple(_rename_node(c, activity_id, label) for c in node.children),
    )


def _remove_node(node: Activity, activity_id: str) -> Activity:
    """Rebuild ``node``'s subtree, dropping the child ``activity_id`` (and its whole subtree)."""
    return Activity(
        id=node.id,
        label=node.label,
        parent_id=node.parent_id,
        children=tuple(_remove_node(c, activity_id) for c in node.children if c.id != activity_id),
    )
