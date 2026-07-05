"""The flush path, driven deterministically through the Claude Code mock.

The mock records tool calls into a real spool, then fires Stop / SessionEnd to flush them into an
injected commit sink — the exact two-phase behaviour the plugin wires up, with no live session.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from sailguarding.sensor.mock import FrozenGit, MockClaudeCode
from sailguarding.sensor.spool import SpoolStorage
from sailguarding.storage import InMemoryStorage


def _record_two_tool_calls(
    mock: MockClaudeCode,
    spool: SpoolStorage,
    git: FrozenGit,
    clock: Callable[[], datetime],
) -> None:
    for tool in ("Edit", "Bash"):
        mock.dispatch_in_process(
            mock.invoke(tool, {"file_path": "a.py"}),
            storage=spool,
            git=git,
            clock=clock,
        )


def test_stop_flushes_the_turns_events_into_the_commit_sink(
    mock: MockClaudeCode,
    frozen_git: FrozenGit,
    clock: Callable[[], datetime],
    tmp_path: Path,
) -> None:
    spool = SpoolStorage(tmp_path / "spool")
    branch = InMemoryStorage()
    _record_two_tool_calls(mock, spool, frozen_git, clock)

    # Nothing committed yet — the tool calls are only staged.
    assert branch.scan() == []
    assert len(spool.read_session("session-1")) == 2

    exit_code = mock.dispatch_flush_in_process(
        mock.stop(), spool=spool, branch=branch, git=frozen_git
    )

    assert exit_code == 0
    assert [r.tool_name for r in branch.read_session("session-1")] == ["Edit", "Bash"]
    # The spool is cleared once committed.
    assert spool.read_session("session-1") == []


def test_session_end_is_a_backstop_after_stop_already_flushed(
    mock: MockClaudeCode,
    frozen_git: FrozenGit,
    clock: Callable[[], datetime],
    tmp_path: Path,
) -> None:
    spool = SpoolStorage(tmp_path / "spool")
    branch = InMemoryStorage()
    _record_two_tool_calls(mock, spool, frozen_git, clock)

    mock.dispatch_flush_in_process(mock.stop(), spool=spool, branch=branch, git=frozen_git)
    # SessionEnd finds an empty spool and adds nothing — no duplicates, no empty batch.
    mock.dispatch_flush_in_process(mock.session_end(), spool=spool, branch=branch, git=frozen_git)

    assert len(branch.scan()) == 2


def test_events_recorded_after_a_flush_are_captured_by_the_next_flush(
    mock: MockClaudeCode,
    frozen_git: FrozenGit,
    clock: Callable[[], datetime],
    tmp_path: Path,
) -> None:
    spool = SpoolStorage(tmp_path / "spool")
    branch = InMemoryStorage()

    # Turn 1: one tool call, then Stop.
    mock.dispatch_in_process(
        mock.invoke("Edit", {"file_path": "a.py"}), storage=spool, git=frozen_git, clock=clock
    )
    mock.dispatch_flush_in_process(mock.stop(), spool=spool, branch=branch, git=frozen_git)

    # Turn 2: another tool call, then Stop again.
    mock.dispatch_in_process(
        mock.invoke("Bash", {"command": "pytest"}), storage=spool, git=frozen_git, clock=clock
    )
    mock.dispatch_flush_in_process(mock.stop(), spool=spool, branch=branch, git=frozen_git)

    assert [r.tool_name for r in branch.scan()] == ["Edit", "Bash"]


def test_flush_is_fail_open_when_the_commit_sink_raises(
    mock: MockClaudeCode,
    frozen_git: FrozenGit,
    clock: Callable[[], datetime],
    tmp_path: Path,
) -> None:
    spool = SpoolStorage(tmp_path / "spool")

    class ExplodingBranch(InMemoryStorage):
        def append_many(self, records: object) -> None:
            raise RuntimeError("branch is down")

    _record_two_tool_calls(mock, spool, frozen_git, clock)

    exit_code = mock.dispatch_flush_in_process(
        mock.stop(), spool=spool, branch=ExplodingBranch(), git=frozen_git
    )

    # Fail-open: the session isn't broken, and the staged events are retained for a retry.
    assert exit_code == 0
    assert len(spool.read_session("session-1")) == 2
