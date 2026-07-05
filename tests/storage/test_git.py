"""Tests for the ``git`` seam in :mod:`sailguarding.storage.git`.

:class:`GitResult` is a pure value type: its behaviour (``ok``, ``text()``) is unit-tested
without any subprocess. :class:`SubprocessGitRunner` is the real shell-out, so it gets one
happy-path integration test against a temporary repo plus a failure case proving it reports
non-zero exits by value rather than raising.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sailguarding.storage import GitError, GitResult, SubprocessGitRunner


@pytest.mark.parametrize(
    ("returncode", "expected_ok"),
    [
        pytest.param(0, True, id="zero-is-ok"),
        pytest.param(1, False, id="one-is-not-ok"),
        pytest.param(128, False, id="git-fatal-is-not-ok"),
    ],
)
def test_ok_reflects_returncode(returncode: int, expected_ok: bool) -> None:
    result = GitResult(returncode=returncode, stdout=b"", stderr=b"")

    assert result.ok is expected_ok


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [
        pytest.param(b"deadbeef\n", "deadbeef", id="trailing-newline-stripped"),
        pytest.param(b"  spaced  ", "spaced", id="surrounding-whitespace-stripped"),
        pytest.param(b"a\nb\n", "a\nb", id="internal-newline-kept"),
    ],
)
def test_text_returns_stripped_stdout_on_success(stdout: bytes, expected: str) -> None:
    result = GitResult(returncode=0, stdout=stdout, stderr=b"")

    assert result.text() == expected


def test_text_raises_git_error_with_stderr_on_failure() -> None:
    result = GitResult(returncode=1, stdout=b"", stderr=b"fatal: not a git repository\n")

    with pytest.raises(GitError, match="not a git repository"):
        result.text()


def test_subprocess_runner_runs_a_real_command(git_repo: Path) -> None:
    runner = SubprocessGitRunner(git_repo)

    result = runner(["rev-parse", "--is-inside-work-tree"])

    assert result.ok
    assert result.returncode == 0
    assert result.text() == "true"


def test_subprocess_runner_passes_stdin(git_repo: Path) -> None:
    runner = SubprocessGitRunner(git_repo)

    result = runner(["hash-object", "-w", "--stdin"], stdin=b"hello\n")

    assert result.ok
    # git hashes "hello\n" to a stable, well-known blob oid.
    assert result.text() == "ce013625030ba8dba906f756967f9e9ca394464a"


def test_subprocess_runner_reports_failure_without_raising(git_repo: Path) -> None:
    runner = SubprocessGitRunner(git_repo)

    result = runner(["cat-file", "-p", "does-not-exist"])

    assert not result.ok
    assert result.returncode != 0
    assert result.stderr != b""


def test_git_helper_fixture_runs_commands(git_repo: Path, git: Callable[..., str]) -> None:
    # The conftest git helper is exercised throughout the branch tests; assert it works.
    assert git(git_repo, "rev-parse", "--is-inside-work-tree") == "true"
