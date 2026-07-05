"""The local staging sink and its drain-on-success semantics."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sailguarding.domain import Context, EventRecord
from sailguarding.sensor.mock import FrozenGit
from sailguarding.sensor.spool import SpoolStorage, resolve_spool_root
from sailguarding.storage.git import GitResult


def _event(session_id: str = "s", tool_name: str = "Edit") -> EventRecord:
    return EventRecord(
        session_id=session_id,
        harness_id="claude-code",
        tool_name=tool_name,
        tool_input={"file_path": "a.py"},
        context=Context(repo="checkout"),
        timestamp=datetime(2026, 7, 5, 12, 30, tzinfo=UTC),
    )


@pytest.fixture
def spool(tmp_path: Path) -> SpoolStorage:
    return SpoolStorage(tmp_path / "spool")


def test_append_then_read_round_trips(spool: SpoolStorage) -> None:
    first, second = _event(tool_name="Edit"), _event(tool_name="Bash")

    spool.append(first)
    spool.append(second)

    assert spool.read_session("s") == [first, second]


def test_staging_writes_no_commit_only_local_files(spool: SpoolStorage, tmp_path: Path) -> None:
    spool.append(_event())

    # The event is a plain local JSONL file — no git anywhere.
    files = list((tmp_path / "spool").rglob("*.jsonl"))
    assert len(files) == 1
    assert files[0].name == "2026-07-05.jsonl"


def test_draining_yields_the_batch_and_clears_on_success(spool: SpoolStorage) -> None:
    spool.append(_event(tool_name="Edit"))
    spool.append(_event(tool_name="Bash"))

    with spool.draining("s") as batch:
        drained = list(batch.records)

    assert [r.tool_name for r in drained] == ["Edit", "Bash"]
    # Cleared: a second drain sees nothing, so a re-flush never double-commits.
    assert spool.read_session("s") == []
    with spool.draining("s") as batch:
        assert batch.records == []


def test_draining_retains_the_batch_when_the_block_raises(spool: SpoolStorage) -> None:
    spool.append(_event())

    with pytest.raises(RuntimeError, match="commit failed"), spool.draining("s") as batch:
        assert len(batch.records) == 1
        raise RuntimeError("commit failed")

    # The staged event survives so the next flush can retry it.
    assert len(spool.read_session("s")) == 1


def test_draining_an_unknown_session_is_empty(spool: SpoolStorage) -> None:
    with spool.draining("never-seen") as batch:
        assert batch.records == []


def test_a_write_during_a_flush_is_not_lost(spool: SpoolStorage) -> None:
    # Claim-by-rename means an event appended after the claim starts a fresh file and survives.
    spool.append(_event(tool_name="Edit"))

    with spool.draining("s") as batch:
        assert [r.tool_name for r in batch.records] == ["Edit"]
        # A concurrent tool call lands mid-flush:
        spool.append(_event(tool_name="Bash"))

    # The first batch was cleared; the concurrent write remains for the next flush.
    assert [r.tool_name for r in spool.read_session("s")] == ["Bash"]


def test_resolve_spool_root_prefers_env_override(tmp_path: Path) -> None:
    git = FrozenGit(toplevel="/repo", branch="main", commit="c0ffee")

    root = resolve_spool_root(git, tmp_path, {"SAILGUARDING_SPOOL_DIR": "/custom/spool"})

    assert root == Path("/custom/spool")


def test_resolve_spool_root_defaults_under_the_git_dir(tmp_path: Path) -> None:
    class GitWithDir:
        """A GitRunner that answers the absolute-git-dir query."""

        def __call__(
            self,
            args: Sequence[str],
            *,
            stdin: bytes | None = None,
            env: Mapping[str, str] | None = None,
        ) -> GitResult:
            if list(args) == ["rev-parse", "--absolute-git-dir"]:
                return GitResult(0, b"/repo/.git\n", b"")
            return GitResult(1, b"", b"unknown\n")

    root = resolve_spool_root(GitWithDir(), tmp_path, {})

    assert root == Path("/repo/.git/sailguarding/spool")


def test_resolve_spool_root_falls_back_outside_git(tmp_path: Path) -> None:
    git = FrozenGit(toplevel="/repo", branch="main", commit="c0ffee")  # no git-dir answer

    root = resolve_spool_root(git, tmp_path, {})

    assert root == tmp_path / ".sailguarding" / "spool"


def test_rejects_invalid_session_id(spool: SpoolStorage) -> None:
    with pytest.raises(ValueError, match="valid spool component"):
        spool.append(_event(session_id="a/b"))


@pytest.mark.parametrize("reader", ["read_day", "scan"])
def test_read_day_and_scan(spool: SpoolStorage, reader: str) -> None:
    event = _event()
    spool.append(event)

    read: Callable[..., list[EventRecord]] = getattr(spool, reader)
    result = read(datetime(2026, 7, 5, tzinfo=UTC).date()) if reader == "read_day" else read()

    assert result == [event]
