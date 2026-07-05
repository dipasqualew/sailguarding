"""The engine CLI entrypoint the Claude Code hook shells into.

The plugin's hook is intentionally thin — it pipes the raw PreToolUse payload here and exits.
All the logic lives in this entrypoint: read the stdin JSON, resolve config from the
environment, wire the default sink / context resolver / redactor, and record one event.

**Fail-open is the whole posture of a sensor.** Recording must never break the user's agent
session, so every failure — a malformed payload, an unreachable git repo, a storage error, a
slow write — is caught here, logged to stderr, and swallowed. The entrypoint always exits ``0``
and never writes to stdout, which Claude Code reads as "no decision, proceed normally". (The
actuator role of this same hook will change that posture *deliberately*, later; the sensor must
not.)

Invoke as ``sailguarding record`` (console script) or ``python -m sailguarding.sensor``.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from sailguarding.domain import EventRecord
from sailguarding.sensor.config import SensorConfig, build_storage
from sailguarding.sensor.context import GitContextResolver
from sailguarding.sensor.payload import parse_payload
from sailguarding.sensor.recorder import record_event
from sailguarding.sensor.redaction import SecretKeyRedactor
from sailguarding.storage import StorageStrategy
from sailguarding.storage.git import GitRunner, SubprocessGitRunner

# CLAUDE_PROJECT_DIR is the harness's own env var for the project root; prefer it over the
# tool's cwd (which may be a subdirectory) as the repo the branch sink targets.
ENV_PROJECT_DIR = "CLAUDE_PROJECT_DIR"


def main(
    argv: list[str] | None = None,
    *,
    stdin: BinaryIO | None = None,
    env: Mapping[str, str] | None = None,
    storage_factory: Callable[[SensorConfig], StorageStrategy] = build_storage,
    git_factory: Callable[[Path], GitRunner] = SubprocessGitRunner,
    clock: Callable[[], datetime] | None = None,
) -> int:
    """Record one PreToolUse event from stdin. Always returns ``0`` (fail-open).

    Injectable ``storage_factory`` / ``git_factory`` / ``clock`` let the deterministic mock
    drive this exact path against an in-memory sink and a fake git, with a frozen clock.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    env = os.environ if env is None else env
    stream: BinaryIO = sys.stdin.buffer if stdin is None else stdin

    if argv and argv[0] != "record":
        # Unknown subcommand: still fail-open, but say so on stderr for the operator.
        print(f"sailguarding sensor: unknown command {argv[0]!r}", file=sys.stderr)
        return 0

    try:
        _record(stream, env, storage_factory, git_factory, clock)
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

    repo_path = Path(env.get(ENV_PROJECT_DIR) or payload.cwd)
    config = SensorConfig.from_env(repo_path, env)

    resolver = GitContextResolver(
        git_factory=git_factory,
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
