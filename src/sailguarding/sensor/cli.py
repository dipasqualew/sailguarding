"""The engine CLI entrypoint the Claude Code hooks shell into.

The plugin's hooks are intentionally thin — they pipe the raw hook payload here and exit. All
the logic lives in this entrypoint. There are two subcommands, one per hook role:

- ``record`` (PreToolUse) — capture the tool call and **stage** it in the local spool. Cheap,
  no git, on the agent's hot path.
- ``flush`` (Stop / SessionEnd) — drain the session's staged events and commit them to the
  branch sink in **one** commit. This is where git work happens: once per agent turn, not once
  per tool call.

**Fail-open is the whole posture of a sensor.** Neither recording nor flushing may break the
user's agent session, so every failure — a malformed payload, an unreachable git repo, a
storage error, a slow write — is caught here, logged to stderr, and swallowed. The entrypoint
always exits ``0`` and never writes to stdout, which Claude Code reads as "no decision, proceed
normally". (The actuator role of the pre-tool-use hook will change that posture *deliberately*,
later; the sensor must not.)

Invoke as ``sailguarding record`` / ``sailguarding flush`` (console script) or
``python -m sailguarding.sensor <command>``.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from sailguarding.domain import EventRecord
from sailguarding.sensor.config import (
    SensorConfig,
    build_branch_storage,
    build_spool_storage,
)
from sailguarding.sensor.context import GitContextResolver
from sailguarding.sensor.payload import parse_payload, parse_session_payload
from sailguarding.sensor.recorder import record_event
from sailguarding.sensor.redaction import SecretKeyRedactor
from sailguarding.sensor.spool import SpoolStorage, resolve_spool_root
from sailguarding.storage import StorageStrategy
from sailguarding.storage.git import GitRunner, SubprocessGitRunner

# CLAUDE_PROJECT_DIR is the harness's own env var for the project root; prefer it over the
# tool's cwd (which may be a subdirectory) as the repo the branch sink targets.
ENV_PROJECT_DIR = "CLAUDE_PROJECT_DIR"

RECORD = "record"
FLUSH = "flush"


def main(
    argv: list[str] | None = None,
    *,
    stdin: BinaryIO | None = None,
    env: Mapping[str, str] | None = None,
    storage_factory: Callable[[SensorConfig], StorageStrategy] = build_spool_storage,
    spool_factory: Callable[[SensorConfig], SpoolStorage] = build_spool_storage,
    branch_factory: Callable[[SensorConfig], StorageStrategy] = build_branch_storage,
    git_factory: Callable[[Path], GitRunner] = SubprocessGitRunner,
    clock: Callable[[], datetime] | None = None,
) -> int:
    """Run one hook command from stdin. Always returns ``0`` (fail-open).

    ``record`` stages via ``storage_factory`` (the spool by default). ``flush`` drains
    ``spool_factory`` and commits through ``branch_factory``. All factories, plus ``git_factory``
    and ``clock``, are injectable so the deterministic mock can drive both paths in-process.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    env = os.environ if env is None else env
    stream: BinaryIO = sys.stdin.buffer if stdin is None else stdin

    command = argv[0] if argv else RECORD

    try:
        if command == RECORD:
            _record(stream, env, storage_factory, git_factory, clock)
        elif command == FLUSH:
            _flush(stream, env, spool_factory, branch_factory, git_factory)
        else:
            print(f"sailguarding sensor: unknown command {command!r}", file=sys.stderr)
    except Exception as exc:  # a sensor must never break the tool call — catch everything.
        # Everything is caught: a bad payload, a git failure, a storage error, anything.
        print(f"sailguarding sensor: {type(exc).__name__}: {exc}", file=sys.stderr)

    return 0


def _record(
    stream: BinaryIO,
    env: Mapping[str, str],
    storage_factory: Callable[[SensorConfig], StorageStrategy],
    git_factory: Callable[[Path], GitRunner],
    clock: Callable[[], datetime] | None,
) -> EventRecord:
    payload = parse_payload(json.loads(stream.read()))

    git, config = _resolve(env, payload.cwd, git_factory)
    resolver = GitContextResolver(
        git_factory=lambda _path: git,
        team=config.team,
        environment=config.environment,
    )
    redactor = SecretKeyRedactor(config.redact_keys)
    storage = storage_factory(config)

    record_kwargs = {} if clock is None else {"clock": clock}
    return record_event(
        payload,
        storage_append=storage.append,
        context_resolver=resolver,
        redactor=redactor,
        **record_kwargs,
    )


def _flush(
    stream: BinaryIO,
    env: Mapping[str, str],
    spool_factory: Callable[[SensorConfig], SpoolStorage],
    branch_factory: Callable[[SensorConfig], StorageStrategy],
    git_factory: Callable[[Path], GitRunner],
) -> None:
    payload = parse_session_payload(json.loads(stream.read()))

    _git, config = _resolve(env, payload.cwd, git_factory)
    spool = spool_factory(config)
    branch = branch_factory(config)

    # Claim the session's staged events and commit them as one batch. The context manager
    # deletes the claimed spool files only if the commit succeeds; a failure leaves them for
    # the next flush to retry. An empty batch commits nothing (no empty commit).
    with spool.draining(payload.session_id) as batch:
        if batch.records:
            branch.append_many(batch.records)


def _resolve(
    env: Mapping[str, str],
    cwd: str,
    git_factory: Callable[[Path], GitRunner],
) -> tuple[GitRunner, SensorConfig]:
    """Build the git runner and the fully-resolved config (including the spool root)."""
    repo_path = Path(env.get(ENV_PROJECT_DIR) or cwd)
    git = git_factory(repo_path)
    config = SensorConfig.from_env(repo_path, env)
    config = replace(config, spool_root=resolve_spool_root(git, repo_path, env))
    return git, config
