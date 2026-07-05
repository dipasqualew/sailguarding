"""A thin, injectable seam over the ``git`` CLI.

The branch sink talks to git only through :class:`GitRunner`, so callers can substitute a
fake in a pure unit test while the real implementation shells out to ``git`` plumbing. The
runner deliberately does *not* raise on a non-zero exit: some plumbing calls (a missing ref,
a missing path) fail by design and the caller wants to inspect ``returncode`` rather than
handle an exception.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class GitError(RuntimeError):
    """A git command that was expected to succeed did not."""


@dataclass(frozen=True)
class GitResult:
    """The outcome of one git invocation."""

    returncode: int
    stdout: bytes
    stderr: bytes

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def text(self) -> str:
        """Stdout as stripped text; raises :class:`GitError` on a non-zero exit."""
        if not self.ok:
            raise GitError(self.stderr.decode(errors="replace").strip())
        return self.stdout.decode().strip()


class GitRunner(Protocol):
    """Runs a git command in a fixed repository and returns its raw result."""

    def __call__(
        self,
        args: Sequence[str],
        *,
        stdin: bytes | None = None,
        env: Mapping[str, str] | None = None,
    ) -> GitResult: ...


class SubprocessGitRunner:
    """A :class:`GitRunner` that shells out to the ``git`` binary."""

    def __init__(self, repo_path: Path, *, git_binary: str = "git") -> None:
        self._repo_path = repo_path
        self._git_binary = git_binary

    def __call__(
        self,
        args: Sequence[str],
        *,
        stdin: bytes | None = None,
        env: Mapping[str, str] | None = None,
    ) -> GitResult:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        proc = subprocess.run(
            [self._git_binary, *args],
            cwd=self._repo_path,
            input=stdin,
            capture_output=True,
            env=merged_env,
            check=False,
        )
        return GitResult(proc.returncode, proc.stdout, proc.stderr)
