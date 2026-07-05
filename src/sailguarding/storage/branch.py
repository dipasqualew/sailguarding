"""A :class:`StorageStrategy` that commits the event log to a branch of the repo.

Storage starts with zero infrastructure: the first real sink is *the repo itself*. Records
are written as JSONL onto a dedicated branch (default ``sailguarding/events``), giving a
versioned, git-native, offline-friendly audit trail. Two design rules keep it honest:

- **Never touch the working branch or tree.** Every write goes straight to the branch ref
  via git plumbing (``hash-object`` → ``write-tree`` → ``commit-tree`` → ``update-ref``)
  against a private, temporary index. The user's checked-out branch, index, and working
  files are never read or modified.
- **Shard to avoid merges.** One append-only file per ``{session_id}/{date}`` shard. Two
  sessions write two different files, so concurrent writers never contend on content. The
  only shared thing is the branch ref, which is advanced with a compare-and-swap retry loop,
  so concurrent commits serialise without losing each other's work.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date
from pathlib import Path

from sailguarding.domain import EventRecord, event_from_json, event_to_json
from sailguarding.storage.git import GitError, GitResult, GitRunner, SubprocessGitRunner

_ZERO_OID = "0" * 40
_BLOB_MODE = "100644"
_MAX_CAS_RETRIES = 25


@dataclass(frozen=True)
class BranchStorageConfig:
    """Where and how the branch sink writes.

    :param repo_path: Path to the git repository whose branch holds the log.
    :param branch: Short name of the dedicated events branch. Kept out of the user's normal
        branch namespace by default so it never collides with feature work.
    :param author_name: Identity recorded on every commit. Supplied explicitly so writes
        succeed in repos with no configured ``user.name``.
    :param author_email: Email recorded on every commit.
    """

    repo_path: Path
    branch: str = "sailguarding/events"
    author_name: str = "sailguarding"
    author_email: str = "sailguarding@localhost"

    @property
    def ref(self) -> str:
        return f"refs/heads/{self.branch}"


class BranchStorage:
    """A :class:`StorageStrategy` persisting the event log to a git branch."""

    def __init__(
        self,
        config: BranchStorageConfig,
        *,
        runner_factory: Callable[[Path], GitRunner] = SubprocessGitRunner,
    ) -> None:
        self._config = config
        self._git = runner_factory(config.repo_path)

    # -- writing ----------------------------------------------------------------

    def append(self, record: EventRecord) -> None:
        self.append_many([record])

    def append_many(self, records: Iterable[EventRecord]) -> None:
        # Group the batch by shard up front: each shard's new lines are appended to whatever
        # that file already holds on the branch, in one commit.
        pending: dict[str, list[str]] = {}
        for record in records:
            pending.setdefault(_shard_path(record), []).append(event_to_json(record))
        if not pending:
            return

        for _ in range(_MAX_CAS_RETRIES):
            parent = self._current_commit()
            tree = self._build_tree(parent, pending)
            commit = self._commit_tree(tree, parent, len(pending))
            if self._advance_ref(commit, parent):
                return
            # The ref moved under us (a concurrent writer won the race). Re-read the branch
            # and rebuild against the new tip so we don't clobber their commit.
        raise GitError(f"could not advance {self._config.ref} after {_MAX_CAS_RETRIES} attempts")

    def _build_tree(self, parent: str | None, pending: dict[str, list[str]]) -> str:
        # A private index file keeps the user's real index untouched. read-tree seeds it from
        # the parent commit (or leaves it empty for the first write); update-index --cacheinfo
        # splices in each new blob at its shard path; write-tree captures the result.
        with _temp_index() as index_env:
            if parent is not None:
                self._run(["read-tree", parent], env=index_env)
            for shard_path, lines in pending.items():
                existing = self._read_blob(parent, shard_path)
                appended = existing + "".join(line + "\n" for line in lines).encode()
                blob = self._hash_object(appended)
                self._run(
                    ["update-index", "--add", "--cacheinfo", f"{_BLOB_MODE},{blob},{shard_path}"],
                    env=index_env,
                )
            return self._run(["write-tree"], env=index_env).text()

    def _commit_tree(self, tree: str, parent: str | None, shard_count: int) -> str:
        args = ["commit-tree", tree]
        if parent is not None:
            args += ["-p", parent]
        message = f"sailguarding: append events to {shard_count} shard(s)"
        args += ["-m", message]
        return self._run(args, env=self._identity_env()).text()

    def _advance_ref(self, new_commit: str, parent: str | None) -> bool:
        # Compare-and-swap: only move the ref if it still points where we branched from
        # (or still does not exist). A losing writer gets returncode != 0 and retries.
        old = parent if parent is not None else _ZERO_OID
        result = self._run(["update-ref", self._config.ref, new_commit, old])
        return result.ok

    # -- reading ----------------------------------------------------------------

    def read_session(self, session_id: str) -> list[EventRecord]:
        prefix = f"{session_id}/"
        return self._read(lambda path: path.startswith(prefix))

    def read_day(self, day: date) -> list[EventRecord]:
        suffix = f"/{day.isoformat()}.jsonl"
        return self._read(lambda path: path.endswith(suffix))

    def scan(self) -> list[EventRecord]:
        return self._read(lambda _path: True)

    def _read(self, select: Callable[[str], bool]) -> list[EventRecord]:
        parent = self._current_commit()
        if parent is None:
            return []
        records: list[EventRecord] = []
        for shard_path in sorted(p for p in self._list_paths(parent) if select(p)):
            blob = self._read_blob(parent, shard_path).decode()
            records.extend(event_from_json(line) for line in blob.splitlines() if line.strip())
        return records

    def _list_paths(self, commit: str) -> list[str]:
        output = self._run(["ls-tree", "-r", "--name-only", commit]).text()
        return output.splitlines() if output else []

    # -- git plumbing helpers ---------------------------------------------------

    def _current_commit(self) -> str | None:
        result = self._run(["rev-parse", "--verify", "--quiet", self._config.ref])
        return result.stdout.decode().strip() or None if result.ok else None

    def _read_blob(self, commit: str | None, shard_path: str) -> bytes:
        if commit is None:
            return b""
        result = self._run(["cat-file", "-p", f"{commit}:{shard_path}"])
        # A missing path means the shard does not exist yet on the branch — start empty.
        return result.stdout if result.ok else b""

    def _hash_object(self, content: bytes) -> str:
        return self._run(["hash-object", "-w", "--stdin"], stdin=content).text()

    def _identity_env(self) -> dict[str, str]:
        name, email = self._config.author_name, self._config.author_email
        return {
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": name,
            "GIT_COMMITTER_EMAIL": email,
        }

    def _run(
        self,
        args: list[str],
        *,
        stdin: bytes | None = None,
        env: dict[str, str] | None = None,
    ) -> GitResult:
        return self._git(args, stdin=stdin, env=env)


def _shard_path(record: EventRecord) -> str:
    session = record.session_id
    if not session or "/" in session or session in {".", ".."}:
        raise ValueError(f"session_id {session!r} is not a valid shard component")
    day = record.timestamp.astimezone(UTC).date().isoformat()
    return f"{session}/{day}.jsonl"


class _temp_index:
    """Context manager yielding a ``GIT_INDEX_FILE`` env pointing at a throwaway index."""

    def __enter__(self) -> dict[str, str]:
        self._dir = tempfile.TemporaryDirectory(prefix="sailguarding-index-")
        return {"GIT_INDEX_FILE": str(Path(self._dir.name) / "index")}

    def __exit__(self, *exc: object) -> None:
        self._dir.cleanup()
