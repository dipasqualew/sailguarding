"""Context resolution: repo + branch + work-unit key, against fake and real git."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sailguarding.sensor.context import GitContextResolver
from sailguarding.sensor.mock import FrozenGit
from sailguarding.sensor.payload import HookPayload
from sailguarding.sensor.workunit import BRANCH_KEY, COMMIT_KEY
from sailguarding.storage.git import SubprocessGitRunner


def _payload(cwd: str) -> HookPayload:
    return HookPayload(session_id="s", tool_name="Edit", tool_input={"file_path": "a.py"}, cwd=cwd)


def test_resolves_repo_branch_and_work_unit_from_git() -> None:
    git = FrozenGit(toplevel="/work/checkout", branch="main", commit="deadbeef")
    resolver = GitContextResolver(git_factory=lambda _p: git)

    context = resolver.resolve(_payload("/work/checkout/src"))

    assert context["repo"] == "checkout"
    assert context[BRANCH_KEY] == "main"
    assert context[COMMIT_KEY] == "deadbeef"


def test_team_and_environment_included_only_when_set() -> None:
    git = FrozenGit(toplevel="/work/checkout", branch="main", commit="deadbeef")

    with_labels = GitContextResolver(
        git_factory=lambda _p: git, team="payments", environment="prod"
    ).resolve(_payload("/work/checkout"))
    without = GitContextResolver(git_factory=lambda _p: git).resolve(_payload("/work/checkout"))

    assert with_labels["team"] == "payments"
    assert with_labels["environment"] == "prod"
    assert "team" not in without
    assert "environment" not in without


def test_falls_back_to_cwd_basename_outside_a_git_repo(tmp_path: Path) -> None:
    # A directory that is not a git repository: no branch/commit, repo name from the cwd.
    resolver = GitContextResolver(git_factory=SubprocessGitRunner)

    context = resolver.resolve(_payload(str(tmp_path)))

    assert context["repo"] == tmp_path.name
    assert BRANCH_KEY not in context
    assert COMMIT_KEY not in context


def test_resolves_against_a_real_git_repo(tmp_path: Path) -> None:
    _run(tmp_path, "init", "-b", "trunk")
    _run(tmp_path, "config", "user.name", "test")
    _run(tmp_path, "config", "user.email", "test@localhost")
    _run(tmp_path, "commit", "--allow-empty", "-m", "initial")
    head = _run(tmp_path, "rev-parse", "HEAD")

    context = GitContextResolver(git_factory=SubprocessGitRunner).resolve(_payload(str(tmp_path)))

    assert context["repo"] == tmp_path.name
    assert context[BRANCH_KEY] == "trunk"
    assert context[COMMIT_KEY] == head


def _run(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True, text=True)
    return proc.stdout.strip()


@pytest.mark.parametrize("subdir", ["", "src", "src/nested"])
def test_repo_name_is_stable_across_subdirectories(tmp_path: Path, subdir: str) -> None:
    _run(tmp_path, "init")
    _run(tmp_path, "config", "user.name", "test")
    _run(tmp_path, "config", "user.email", "test@localhost")
    _run(tmp_path, "commit", "--allow-empty", "-m", "initial")
    workdir = tmp_path / subdir
    workdir.mkdir(parents=True, exist_ok=True)

    context = GitContextResolver(git_factory=SubprocessGitRunner).resolve(_payload(str(workdir)))

    assert context["repo"] == tmp_path.name
