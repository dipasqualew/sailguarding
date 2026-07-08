"""End-to-end: the real shell hook → engine → spool → flush → branch sink, over a subprocess.

The in-process tests inject the sinks; this one runs the *actual* plugin hook script exactly as
Claude Code invokes it — as a subprocess, with the hook payload on stdin and the plugin
environment set — against a real temporary git repo. It proves the whole wiring end to end:

- ``hook.sh record`` (PreToolUse) stages events in the spool and does *not* commit,
- ``hook.sh flush`` (Stop / SessionEnd) commits a whole session's staged events in one commit,
- and both are fail-open.

This is the closest CI can get to "a real Claude Code session produces EventRecords in the
branch sink".
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from sailguarding.storage import BranchStorage, BranchStorageConfig

# The real plugin hook script, resolved relative to the repo root (…/tests/sensor/ -> repo).
REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_SCRIPT = REPO_ROOT / "plugins" / "claude-code" / "bin" / "hook.sh"

# Drive the engine as a module so the test doesn't depend on the console script being on PATH.
ENGINE_COMMAND = f"{sys.executable} -m sailguarding.sensor"

SESSION = "e2e-session"


def _init_repo(path: Path) -> None:
    def run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=path, capture_output=True, check=True)

    run("init", "-b", "trunk")
    run("config", "user.name", "test")
    run("config", "user.email", "test@localhost")
    run("commit", "--allow-empty", "-m", "initial")


def _tool_payload(cwd: Path, tool_name: str, tool_input: dict[str, object]) -> bytes:
    return json.dumps(
        {
            "session_id": SESSION,
            "cwd": str(cwd),
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": tool_input,
        }
    ).encode()


def _stop_payload(cwd: Path) -> bytes:
    return json.dumps({"session_id": SESSION, "cwd": str(cwd), "hook_event_name": "Stop"}).encode()


def _run_hook(
    cwd: Path, *, subcommand: str, payload: bytes, engine: str = ENGINE_COMMAND
) -> subprocess.CompletedProcess[bytes]:
    import os

    env = {
        "PATH": os.environ.get("PATH", ""),
        "CLAUDE_PLUGIN_ROOT": str(HOOK_SCRIPT.parent.parent),
        "CLAUDE_PROJECT_DIR": str(cwd),
        "SAILGUARDING_ENGINE": engine,
        # Pin the operator config to a path inside the temp repo so the sensor never reads the
        # developer's real ~/.config file — this test asserts the default (branch) store.
        "SAILGUARDING_CONFIG": str(cwd / "sg-config.json"),
        # Keep the module importable in the subprocess.
        "PYTHONPATH": str(REPO_ROOT / "src"),
    }
    return subprocess.run(
        [str(HOOK_SCRIPT), subcommand], input=payload, env=env, capture_output=True, cwd=str(cwd)
    )


def _branch(cwd: Path) -> BranchStorage:
    return BranchStorage(BranchStorageConfig(repo_path=cwd))


def test_record_stages_without_committing_then_flush_commits(tmp_path: Path) -> None:
    _init_repo(tmp_path)

    # Two tool calls in the "turn": both are recorded (staged), neither commits to the branch.
    r1 = _run_hook(
        tmp_path,
        subcommand="record",
        payload=_tool_payload(tmp_path, "Edit", {"file_path": "a.py", "content": "x"}),
    )
    r2 = _run_hook(
        tmp_path,
        subcommand="record",
        payload=_tool_payload(tmp_path, "Bash", {"command": "pytest"}),
    )
    assert r1.returncode == 0 and r1.stdout == b""
    assert r2.returncode == 0 and r2.stdout == b""

    # Nothing on the branch yet — the deferred commit hasn't happened.
    assert _branch(tmp_path).read_session(SESSION) == []

    # Stop flushes: both staged events land in the branch sink in ONE commit.
    commits_before = _commit_count(tmp_path)
    flush = _run_hook(tmp_path, subcommand="flush", payload=_stop_payload(tmp_path))
    assert flush.returncode == 0 and flush.stdout == b""

    records = _branch(tmp_path).read_session(SESSION)
    assert [r.tool_name for r in records] == ["Edit", "Bash"]
    assert records[0].context["git_branch"] == "trunk"
    assert records[0].context["git_commit"]
    assert _commit_count(tmp_path) == commits_before + 1  # one commit for the whole turn


def test_flush_with_nothing_staged_makes_no_commit(tmp_path: Path) -> None:
    _init_repo(tmp_path)

    # A flush with an empty spool must not create an (empty) commit or a branch.
    result = _run_hook(tmp_path, subcommand="flush", payload=_stop_payload(tmp_path))

    assert result.returncode == 0
    assert _branch(tmp_path).read_session(SESSION) == []


def test_flush_never_dirties_the_working_tree(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _run_hook(
        tmp_path,
        subcommand="record",
        payload=_tool_payload(tmp_path, "Edit", {"file_path": "a.py", "content": "x"}),
    )
    branch_before = _git(tmp_path, "rev-parse", "--abbrev-ref", "HEAD")
    head_before = _git(tmp_path, "rev-parse", "HEAD")

    _run_hook(tmp_path, subcommand="flush", payload=_stop_payload(tmp_path))

    assert _git(tmp_path, "status", "--porcelain") == ""
    assert _git(tmp_path, "rev-parse", "--abbrev-ref", "HEAD") == branch_before
    assert _git(tmp_path, "rev-parse", "HEAD") == head_before


def test_hooks_are_fail_open_when_the_engine_is_broken(tmp_path: Path) -> None:
    _init_repo(tmp_path)

    # A bogus engine command guarantees the invocation fails; both hooks must still exit 0.
    record = _run_hook(
        tmp_path,
        subcommand="record",
        payload=_tool_payload(tmp_path, "Edit", {"file_path": "a.py"}),
        engine="this-engine-does-not-exist",
    )
    flush = _run_hook(
        tmp_path,
        subcommand="flush",
        payload=_stop_payload(tmp_path),
        engine="this-engine-does-not-exist",
    )

    assert record.returncode == 0 and record.stdout == b""
    assert flush.returncode == 0 and flush.stdout == b""


@pytest.fixture(autouse=True)
def _require_hook_script() -> None:
    if not HOOK_SCRIPT.exists():
        pytest.skip(f"hook script not found at {HOOK_SCRIPT}")


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True, text=True)
    return proc.stdout.strip()


def _commit_count(repo: Path) -> int:
    result = subprocess.run(
        ["git", "rev-list", "--count", "sailguarding/events"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip()) if result.returncode == 0 else 0
