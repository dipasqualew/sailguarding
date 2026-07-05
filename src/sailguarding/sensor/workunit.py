"""The work-unit correlation seam.

The hook fires **per tool call**, so the finest-grained thing the sensor can capture is one
:class:`~sailguarding.domain.EventRecord` per call. But a single ``Edit`` is too small to
*judge*: safeguards score in ``[0, 1]`` and need an outcome attached to a coherent **unit of
work**, not to an isolated tool call. Capturing that outcome and scoring it is a later task
(evidence ingestion + scoring); what this task must not skip is the **seam** that lets those
later tasks group per-tool-call events into the unit they contributed to.

Because :class:`~sailguarding.domain.Context` is an open bag of dimensions, the work-unit key
rides along *as context* — no schema change. A :class:`WorkUnitResolver` returns the
dimensions that identify the unit of work in progress at capture time. The first boundary is
a **git commit** (:class:`CommitWorkUnit`): a run of tool calls lands in, or is reverted
from, one reviewable, outcome-bearing commit. It is deliberately a strategy, not a baked-in
definition — a commit is the first unit of work, not the only one.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from sailguarding.domain.context import DimensionValue
from sailguarding.storage.git import GitRunner

# Context-dimension keys under which the git work-unit key is carried. Downstream joins read
# these to attribute a per-tool-call event to the commit-sized unit it lands in.
BRANCH_KEY = "git_branch"
COMMIT_KEY = "git_commit"


@runtime_checkable
class WorkUnitResolver(Protocol):
    """Resolves the correlation key for the unit of work a tool call contributes to.

    Returns context dimensions (JSON scalars) merged into the event's context. Kept behind
    an interface so the definition of "unit of work" can change — a commit today, a PR or a
    ticket tomorrow — without touching the event schema or the sensor.
    """

    def dimensions(self, git: GitRunner) -> Mapping[str, DimensionValue]:
        """Dimensions identifying the current unit of work; empty if none can be resolved."""
        ...


class CommitWorkUnit:
    """Correlates events to the **git commit** they will land in.

    Captures the branch and HEAD commit at tool-call time. Later tasks group every event
    sharing a ``(branch, commit)`` into one revertable, CI-scored unit and attribute the
    safeguard's effectiveness to that unit's outcome. Resolution is best-effort: a repo with
    no commits yet (unborn HEAD) simply yields whatever git can answer, since a sensor must
    never fail a tool call to compute its own bookkeeping.
    """

    def dimensions(self, git: GitRunner) -> Mapping[str, DimensionValue]:
        dims: dict[str, DimensionValue] = {}
        branch = _git_line(git, "rev-parse", "--abbrev-ref", "HEAD")
        if branch:
            dims[BRANCH_KEY] = branch
        commit = _git_line(git, "rev-parse", "HEAD")
        if commit:
            dims[COMMIT_KEY] = commit
        return dims


def _git_line(git: GitRunner, *args: str) -> str | None:
    """Run a git query and return its single stripped line, or ``None`` on any failure."""
    result = git(list(args))
    if not result.ok:
        return None
    return result.stdout.decode(errors="replace").strip() or None
