"""The governance model — the aggregate that ties the tree to its risks and safeguards.

Where :mod:`sailguarding.tree` gives a persistable :class:`~sailguarding.tree.ActivityTree` of bare
nodes, this package adds the governance *around* the tree as one frozen value object,
:class:`ActivityModel`:

- a reusable :class:`Risk` library — hazards ("data loss", "opportunity cost") named once and
  referenced from many activities;
- the reusable :class:`~sailguarding.safeguards.Safeguard` library, shared the same way;
- and the **edges** between activities, risks, and safeguards — which risks an activity faces, and
  which safeguard mitigates which risk on which activity.

Every transform on :class:`ActivityModel` is pure and value-returning (a new model, never a
mutation), the whole aggregate is versioned and round-trip stable, and an injectable
:class:`ActivityModelStore` (:class:`InMemoryActivityModelStore` by default,
:class:`FileActivityModelStore` for durable atomic persistence) saves and reloads it.
"""

from sailguarding.model.model import (
    DEFAULT_MODEL_ID,
    MODEL_SCHEMA_VERSION,
    ROOT_ID,
    ActivityModel,
)
from sailguarding.model.risk import RISK_SCHEMA_VERSION, Risk
from sailguarding.model.scope import (
    SCOPE_SCHEMA_VERSION,
    ContextScope,
    DimensionConstraint,
)
from sailguarding.model.store import (
    ActivityModelStore,
    FileActivityModelStore,
    FileWorkspaceStore,
    InMemoryActivityModelStore,
    InMemoryWorkspaceStore,
    WorkspaceStore,
)
from sailguarding.model.workspace import (
    WORKSPACE_SCHEMA_VERSION,
    ImportKind,
    Workspace,
)

__all__ = [
    "DEFAULT_MODEL_ID",
    "MODEL_SCHEMA_VERSION",
    "RISK_SCHEMA_VERSION",
    "ROOT_ID",
    "SCOPE_SCHEMA_VERSION",
    "WORKSPACE_SCHEMA_VERSION",
    "ActivityModel",
    "ActivityModelStore",
    "ContextScope",
    "DimensionConstraint",
    "FileActivityModelStore",
    "FileWorkspaceStore",
    "ImportKind",
    "InMemoryActivityModelStore",
    "InMemoryWorkspaceStore",
    "Risk",
    "Workspace",
    "WorkspaceStore",
]
