"""A :class:`StorageStrategy` that persists the event log as JSONL under a directory.

The branch sink is the git-native default, but not every repo is a git repo and some teams would
rather point the log at a plain directory — a shared mount, an external volume, a scratch path for
a non-git tree. :class:`FilesystemStorage` is that alternative backend: the same sharded,
append-only JSONL layout as the branch sink, written straight to the filesystem with no git.

It follows the same two rules as every sink:

- **Round-trip.** A record written and read back is equal; the encoding is the one canonical JSON
  from :mod:`sailguarding.domain.serialization`.
- **Shard to avoid merges.** One append-only file per ``{session_id}/{date}`` shard, so two
  sessions never write the same file.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date
from pathlib import Path

from sailguarding.domain import EventRecord, event_from_json, event_to_json


class FilesystemStorage:
    """A :class:`StorageStrategy` writing the event log as JSONL shards under ``root``."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    # -- writing ----------------------------------------------------------------

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
        return _read_paths(sorted(session_dir.glob("*.jsonl")))

    def read_day(self, day: date) -> list[EventRecord]:
        return _read_paths(sorted(self._root.glob(f"*/{day.isoformat()}.jsonl")))

    def scan(self) -> list[EventRecord]:
        return _read_paths(sorted(self._root.glob("*/*.jsonl")))


def _read_paths(paths: Iterable[Path]) -> list[EventRecord]:
    records: list[EventRecord] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        records.extend(event_from_json(line) for line in text.splitlines() if line.strip())
    return records


def _session_dirname(session_id: str) -> str:
    if not session_id or "/" in session_id or session_id in {".", ".."}:
        raise ValueError(f"session_id {session_id!r} is not a valid shard component")
    return session_id


def _day(record: EventRecord) -> str:
    return record.timestamp.astimezone(UTC).date().isoformat()
