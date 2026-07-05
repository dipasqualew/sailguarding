"""Resolving the :class:`~sailguarding.domain.Context` a tool call ran in.

The sensor captures *where* the agent acted, not just *what* it did — because every safeguard
downstream binds to context via a selector. For the software use case that means, at minimum,
the **repo** and the **git branch**; **team** and **environment** are added where the harness
environment makes them available. The **work-unit correlation key** (branch + HEAD commit)
rides along too, contributed by an injectable
:class:`~sailguarding.sensor.workunit.WorkUnitResolver`.

Everything git-derived flows through the same injectable
:class:`~sailguarding.storage.git.GitRunner` the branch sink uses, so a test can substitute a
fake and resolve a fully deterministic context with **no live git branch required** — exactly
what the deterministic mock relies on.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol, runtime_checkable

from sailguarding.domain.context import Context
from sailguarding.sensor.payload import HookPayload
from sailguarding.sensor.workunit import CommitWorkUnit, WorkUnitResolver
from sailguarding.storage.git import GitRunner, SubprocessGitRunner


@runtime_checkable
class ContextResolver(Protocol):
    """Resolves the context a :class:`HookPayload` ran in."""

    def resolve(self, payload: HookPayload) -> Context: ...


class GitContextResolver:
    """Resolves context from the git repository the tool call runs in, plus ambient labels.

    :param git_factory: Builds a :class:`GitRunner` for a given repo path. Injectable so tests
        can provide a fake and callers get the real subprocess runner by default.
    :param team: Ambient team label, when known (typically from the environment).
    :param environment: Ambient environment label (e.g. ``"production"``), when known.
    :param work_unit: Strategy contributing the work-unit correlation key. Defaults to the
        git-commit boundary.
    """

    def __init__(
        self,
        *,
        git_factory: Callable[[Path], GitRunner] = SubprocessGitRunner,
        team: str | None = None,
        environment: str | None = None,
        work_unit: WorkUnitResolver | None = None,
    ) -> None:
        self._git_factory = git_factory
        self._team = team
        self._environment = environment
        self._work_unit = work_unit if work_unit is not None else CommitWorkUnit()

    def resolve(self, payload: HookPayload) -> Context:
        git = self._git_factory(Path(payload.cwd))

        dimensions: dict[str, str | int | float | bool] = {}
        repo = _repo_name(git, payload.cwd)
        if repo:
            dimensions["repo"] = repo
        if self._team:
            dimensions["team"] = self._team
        if self._environment:
            dimensions["environment"] = self._environment

        # The work-unit key (branch + commit) is context too — merged in, no schema change.
        dimensions.update(self._work_unit.dimensions(git))

        return Context(dimensions)


def _repo_name(git: GitRunner, cwd: str) -> str | None:
    """Repository name: the basename of the git top-level, falling back to the cwd basename."""
    result = git(["rev-parse", "--show-toplevel"])
    if result.ok:
        toplevel = result.stdout.decode(errors="replace").strip()
        if toplevel:
            return Path(toplevel).name
    # Not a git repo (or git unavailable): the working directory's name is the best we have.
    name = Path(cwd).name
    return name or None
