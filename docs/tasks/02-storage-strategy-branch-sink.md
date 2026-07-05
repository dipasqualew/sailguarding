# 02 — Storage strategy: branch sink

**Status:** done
**Depends on:** 01

## Context

Observations have to land somewhere. Storage is a **pluggable strategy**, not a fixed backend, so the
engine can start with zero infrastructure and grow into a real store later. The first implementation
writes to a **branch of the repo**: versioned, git-native audit trail, works offline,
open-source-friendly.

Two constraints from the SPEC shape the design:

- **The event log is not the metrics.** Git is a fine append-only log and a terrible time-series
  database. This task delivers the **event log** sink only. Derived safeguard metrics get their own
  (separate, pluggable) sink later — do not conflate them here.
- **Sharding avoids merges.** Many sessions appending to one file means merge conflicts. Write **one
  append-only JSONL file per session per day**; nothing is shared, so nothing has to merge.

## Scope

- **`StorageStrategy` interface** for appending `EventRecord`s and reading them back (by session, by
  day, and a full scan). Interface is what task 03 depends on — keep it minimal and injectable.
- **Branch sink implementation:**
  - Writes `EventRecord`s as JSONL, one file per `{session_id}/{date}` shard.
  - Commits to a dedicated, configurable branch (e.g. `sailguarding/events`) without disturbing the
    working branch or tree.
  - Append is atomic per record and safe under concurrent sessions (separate shards → no contention).
- **In-memory sink** implementing the same interface, for fast tests and as the injectable default in
  unit tests elsewhere.
- **Config** for branch name and repo path, with sane defaults.

## Out of scope

- Derived-metrics sink (later task) — only the raw event log here.
- Non-git backends (enterprise; later).
- Reading outcomes/CI evidence (evidence ingestion is a later task).

## Acceptance criteria

- `StorageStrategy` interface defined; both branch and in-memory sinks implement it.
- Writing N records across two concurrent sessions produces two shard files and zero merge conflicts.
- Records survive a round-trip: append then read-back yields byte-equivalent `EventRecord`s.
- Branch sink never modifies the working branch or leaves the working tree dirty.
- All behaviour covered by tests using dependency injection (inject the sink; no global state).

## Notes

- Prefer writing shards and committing via a git library or plumbing that targets the branch ref
  directly, so the user's checked-out branch and working tree are untouched.
