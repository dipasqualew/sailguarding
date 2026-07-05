"""A deterministic Claude Code stand-in that drives the sensor through the real hook contract.

The sensor path is otherwise only exercisable by a live agent session, which is neither
deterministic nor available in CI. This mock is the substitute: it drives the plugin *exactly*
the way Claude Code's PreToolUse hook does — building the same stdin JSON (``session_id``,
``tool_name``, ``tool_input`` …) and the same environment (``CLAUDE_PROJECT_DIR``,
``CLAUDE_PLUGIN_ROOT``) the real harness passes — so the mock and the plugin cannot drift from
the pinned contract in :mod:`sailguarding.sensor.payload`.

Two dispatch paths, one contract:

- :meth:`MockClaudeCode.dispatch_in_process` runs the engine entrypoint in-process with an
  injected in-memory sink, fake git and frozen clock, so a test can assert the captured record
  byte-for-byte with **no live session and no git branch**.
- :meth:`MockClaudeCode.build_stdin` / :meth:`MockClaudeCode.build_env` expose the raw payload
  and environment, so an end-to-end test can feed them to the real shell hook over a subprocess
  and prove the whole plugin → engine → branch-sink wiring.

:class:`FrozenGit` is the fake git the in-process path uses: a :class:`GitRunner` that answers
the handful of queries context resolution makes with fixed values.
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sailguarding.sensor.cli import ENV_PROJECT_DIR, main
from sailguarding.sensor.payload import PRE_TOOL_USE
from sailguarding.storage import InMemoryStorage, StorageStrategy
from sailguarding.storage.git import GitResult, GitRunner

# Env var Claude Code sets to the plugin's install directory; the hook resolves its script
# path from it. The mock sets it so the environment matches a real plugin invocation.
ENV_PLUGIN_ROOT = "CLAUDE_PLUGIN_ROOT"


@dataclass(frozen=True)
class PreToolUseInvocation:
    """One simulated PreToolUse call: the payload Claude Code would write to the hook's stdin."""

    session_id: str
    tool_name: str
    tool_input: Mapping[str, Any]
    cwd: str
    transcript_path: str
    permission_mode: str

    def payload(self) -> dict[str, Any]:
        """The exact JSON object the harness serialises to the hook's stdin."""
        return {
            "session_id": self.session_id,
            "transcript_path": self.transcript_path,
            "cwd": self.cwd,
            "permission_mode": self.permission_mode,
            "hook_event_name": PRE_TOOL_USE,
            "tool_name": self.tool_name,
            "tool_input": dict(self.tool_input),
        }

    def stdin_bytes(self) -> bytes:
        return json.dumps(self.payload()).encode()


@dataclass
class MockClaudeCode:
    """Drives the sensor as Claude Code's PreToolUse hook would.

    :param cwd: Working directory the simulated tool calls run in.
    :param session_id: Session id stamped on every invocation.
    :param plugin_root: Value of ``CLAUDE_PLUGIN_ROOT`` in the simulated environment.
    :param project_dir: Value of ``CLAUDE_PROJECT_DIR``; defaults to ``cwd``.
    """

    cwd: str
    session_id: str = "mock-session"
    plugin_root: str = "/mock/plugins/sailguarding"
    project_dir: str | None = None
    transcript_path: str = "/mock/transcript.jsonl"
    permission_mode: str = "default"
    base_env: Mapping[str, str] = field(default_factory=dict)

    def invoke(
        self,
        tool_name: str,
        tool_input: Mapping[str, Any],
    ) -> PreToolUseInvocation:
        """Build a PreToolUse invocation for a simulated ``tool_name`` call."""
        return PreToolUseInvocation(
            session_id=self.session_id,
            tool_name=tool_name,
            tool_input=dict(tool_input),
            cwd=self.cwd,
            transcript_path=self.transcript_path,
            permission_mode=self.permission_mode,
        )

    def build_env(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        """The environment Claude Code exposes to the hook, plus any test overrides."""
        env: dict[str, str] = dict(self.base_env)
        env[ENV_PLUGIN_ROOT] = self.plugin_root
        env[ENV_PROJECT_DIR] = self.project_dir or self.cwd
        if extra:
            env.update(extra)
        return env

    def dispatch_in_process(
        self,
        invocation: PreToolUseInvocation,
        *,
        storage: StorageStrategy | None = None,
        git: GitRunner | None = None,
        clock: Callable[[], datetime] | None = None,
        env: Mapping[str, str] | None = None,
    ) -> int:
        """Run the engine entrypoint in-process against an injected sink; return its exit code.

        This exercises the real path — stdin JSON parse → payload → context → redaction →
        record → append — with the sink, git and clock injected for determinism.
        """
        sink = storage if storage is not None else InMemoryStorage()
        return main(
            ["record"],
            stdin=io.BytesIO(invocation.stdin_bytes()),
            env=dict(env) if env is not None else self.build_env(),
            storage_factory=lambda _config: sink,
            git_factory=(lambda _path: git) if git is not None else _default_git_factory,
            clock=clock,
        )


class FrozenGit:
    """A :class:`GitRunner` answering context queries with fixed values — no real git.

    Covers exactly the queries context resolution makes: ``rev-parse --show-toplevel`` (repo
    name), ``rev-parse --abbrev-ref HEAD`` (branch) and ``rev-parse HEAD`` (commit). Any other
    command returns a non-zero result, which the sensor treats as "unavailable".
    """

    def __init__(self, *, toplevel: str, branch: str, commit: str) -> None:
        self._answers: dict[tuple[str, ...], str] = {
            ("rev-parse", "--show-toplevel"): toplevel,
            ("rev-parse", "--abbrev-ref", "HEAD"): branch,
            ("rev-parse", "HEAD"): commit,
        }

    def __call__(
        self,
        args: object,
        *,
        stdin: bytes | None = None,
        env: Mapping[str, str] | None = None,
    ) -> GitResult:
        key = tuple(args) if isinstance(args, (list, tuple)) else (str(args),)
        answer = self._answers.get(key)
        if answer is None:
            return GitResult(returncode=1, stdout=b"", stderr=b"unknown command\n")
        return GitResult(returncode=0, stdout=(answer + "\n").encode(), stderr=b"")


def _default_git_factory(path: Path) -> GitRunner:
    # When a test doesn't inject git, resolve against the real repo at ``path``. Imported
    # lazily-by-reference to keep the fake path free of any subprocess use.
    from sailguarding.storage.git import SubprocessGitRunner

    return SubprocessGitRunner(path)
