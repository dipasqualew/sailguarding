"""A local staging sink so the branch commit can be deferred to Stop / SessionEnd.

Committing to git on **every** tool call is a lot of git work on the agent's hot path (git is a
fine append-only log and a poor high-frequency store). The preference is to commit once per
agent turn instead. But a pre-tool-use hook is a short-lived process — nothing survives in
memory between tool calls — so events captured during a turn have to be **staged on disk** and
committed later by a separate hook.

:class:`SpoolStorage` is that staging area: a :class:`~sailguarding.storage.base.StorageStrategy`
that appends events as JSONL to a local spool directory (default: under the repo's git dir, so it
never touches the working tree and stays offline). It is deliberately cheap — no git — so the
PreToolUse path stays fast and fail-open.

The flush side drains a session with :meth:`SpoolStorage.draining`, a context manager that
**claims** the session's spool files by atomic rename, hands the batch to the caller to commit,
and deletes them only if the caller's block completes without error. So:

- a concurrent tool call that writes mid-flush starts a fresh file and is never lost,
- a failed commit leaves the claimed files in place to be retried on the next flush,
- nothing is deleted until it is safely committed.
"""

from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, date
from pathlib import Path

from sailguarding.domain import EventRecord, event_from_json, event_to_json
from sailguarding.storage.git import GitRunner

# Environment override for where events are staged. Defaults to a path under the git dir.
ENV_SPOOL_DIR = "SAILGUARDING_SPOOL_DIR"

# Suffix marking a spool file that has been claimed for a flush in progress (or a prior,
# failed flush awaiting retry).
_DRAINING_SUFFIX = ".draining"


class SpoolStorage:
    """A :class:`StorageStrategy` that stages events as JSONL under a local directory.

    Layout mirrors the branch sink: one append-only file per ``{session_id}/{date}`` shard, so
    a flush of one session touches only that session's files and concurrent sessions never
    contend.
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    # -- writing (the cheap, per-tool-call path) --------------------------------

    def append(self, record: EventRecord) -> None:
        self.append_many([record])

    def append_many(self, records: Iterable[EventRecord]) -> None:
        for record in records:
            path = self._root / _session_dirname(record.session_id) / f"{_day(record)}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(event_to_json(record) + "\n")

    # -- reading ----------------------------------------------------------------

    def read_session(self, session_id: str) -> list[EventRecord]:
        session_dir = self._root / _session_dirname(session_id)
        return _read_paths(_staged(session_dir, "*.jsonl"))

    def read_day(self, day: date) -> list[EventRecord]:
        return _read_paths(_staged(self._root, f"*/{day.isoformat()}.jsonl"))

    def scan(self) -> list[EventRecord]:
        return _read_paths(_staged(self._root, "*/*.jsonl"))

    # -- draining (the flush path) ----------------------------------------------

    @contextmanager
    def draining(self, session_id: str) -> Iterator[DrainBatch]:
        """Claim a session's staged events for a flush, deleting them only on clean exit.

        Yields a :class:`DrainBatch` of the claimed records. If the ``with`` block raises
        (e.g. the git commit fails), the claimed files are left in place and picked up by the
        next flush; otherwise they are removed once the block completes.
        """
        session_dir = self._root / _session_dirname(session_id)
        claimed = _claim(session_dir)
        yield DrainBatch(records=_read_paths(claimed))
        # Reached only when the caller's block succeeds: the batch is committed, so drop it.
        for path in claimed:
            path.unlink(missing_ok=True)
        _prune_empty_dir(session_dir)


class DrainBatch:
    """The staged records claimed for one flush."""

    def __init__(self, records: list[EventRecord]) -> None:
        self.records = records


def resolve_spool_root(git: GitRunner, repo_path: Path, env: object) -> Path:
    """Where events are staged: an explicit override, else a path under the repo's git dir.

    Staging under the git dir keeps the spool out of the working tree entirely — it never shows
    up in ``git status`` and can never be committed to a working branch by accident — while
    staying repo-local and offline.
    """
    override = _env_get(env, ENV_SPOOL_DIR)
    if override:
        return Path(override)
    result = git(["rev-parse", "--absolute-git-dir"])
    if result.ok:
        git_dir = result.stdout.decode(errors="replace").strip()
        if git_dir:
            return Path(git_dir) / "sailguarding" / "spool"
    # Not a git repo (or git unavailable): fall back to a dotdir in the working directory.
    return Path(repo_path) / ".sailguarding" / "spool"


def _claim(session_dir: Path) -> list[Path]:
    """Atomically rename a session's shard files aside so writers start fresh; return them.

    Includes any leftover ``*.draining`` files from a previous, failed flush so they are
    retried. Rename is atomic, so a concurrent writer either wrote before the claim (its bytes
    are claimed) or after (it creates a new shard file the claim never saw).
    """
    if not session_dir.is_dir():
        return []
    token = f"{os.getpid()}-{time.time_ns()}"
    for shard in sorted(session_dir.glob("*.jsonl")):
        shard.rename(shard.with_name(f"{shard.name}.{token}{_DRAINING_SUFFIX}"))
    return sorted(session_dir.glob(f"*{_DRAINING_SUFFIX}"))


def _staged(base: Path, pattern: str) -> list[Path]:
    """All staged shard files matching ``pattern``, including those claimed by an in-flight or
    previously-failed flush (``*.draining``) — so a read reflects everything not yet committed.

    Sorted so a committed shard's original name sorts before its ``.draining`` rename, preserving
    append order across a retry.
    """
    committed = base.glob(pattern)
    draining = base.glob(f"{pattern}.*{_DRAINING_SUFFIX}")
    return sorted([*committed, *draining])


def _read_paths(paths: Iterable[Path]) -> list[EventRecord]:
    records: list[EventRecord] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        records.extend(event_from_json(line) for line in text.splitlines() if line.strip())
    return records


def _prune_empty_dir(session_dir: Path) -> None:
    # Not empty (a concurrent write landed) or already gone — nothing to clean up.
    with contextlib.suppress(OSError):
        session_dir.rmdir()


def _session_dirname(session_id: str) -> str:
    if not session_id or "/" in session_id or session_id in {".", ".."}:
        raise ValueError(f"session_id {session_id!r} is not a valid spool component")
    return session_id


def _day(record: EventRecord) -> str:
    return record.timestamp.astimezone(UTC).date().isoformat()


def _env_get(env: object, key: str) -> str | None:
    # env is a Mapping[str, str] in practice; typed loosely to avoid an import cycle.
    if isinstance(env, dict):
        value = env.get(key)
        return value if isinstance(value, str) and value else None
    getter = getattr(env, "get", None)
    if getter is None:
        return None
    value = getter(key)
    return value if isinstance(value, str) and value else None
