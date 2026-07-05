"""Shared fixtures for the storage tests.

The builders here mirror the domain conftest: they hand back fully-formed
:class:`EventRecord`s so each test can compose the exact scenario it needs (a given
session, a given UTC day) without repeating the field soup. Nothing is shared mutable
state — every call produces a fresh, immutable record.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sailguarding.domain import Context, EventRecord
from sailguarding.storage import BranchStorage, BranchStorageConfig


def make_event(
    *,
    session_id: str = "session-1",
    timestamp: datetime | None = None,
    tool_name: str = "Edit",
    action_id: str | None = None,
) -> EventRecord:
    """Build a representative :class:`EventRecord` with sensible defaults."""
    return EventRecord(
        session_id=session_id,
        harness_id="claude-code",
        tool_name=tool_name,
        tool_input={"file_path": "checkout.py", "content": "print('hi')"},
        context=Context(team="core", repo="checkout"),
        timestamp=timestamp if timestamp is not None else datetime(2026, 7, 5, 12, 30, tzinfo=UTC),
        action_id=action_id,
    )


@pytest.fixture
def event_factory() -> Callable[..., EventRecord]:
    """Expose :func:`make_event` as an injectable factory."""
    return make_event


def _git(repo: Path, *args: str, stdin: bytes | None = None) -> str:
    """Run a plain ``git`` command in ``repo`` and return stripped stdout, raising on error."""
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        input=stdin,
        capture_output=True,
        check=True,
    )
    return proc.stdout.decode().strip()


@pytest.fixture
def git() -> Callable[..., str]:
    """A helper for running raw ``git`` commands against a repo in assertions/setup."""
    return _git


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A freshly initialised git repo with one empty commit on the default branch.

    The empty initial commit gives the working branch a tip so ``git status`` and
    ``rev-parse --abbrev-ref HEAD`` behave normally, letting tests prove the branch sink
    never disturbs it.
    """
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "config", "user.email", "test@localhost")
    _git(tmp_path, "commit", "--allow-empty", "-m", "initial")
    return tmp_path


@pytest.fixture
def storage(git_repo: Path) -> Iterator[BranchStorage]:
    """A :class:`BranchStorage` wired to the temporary repo, using default config."""
    yield BranchStorage(BranchStorageConfig(repo_path=git_repo))
