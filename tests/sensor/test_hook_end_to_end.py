"""End-to-end: the real shell hook → engine → branch sink, over a subprocess.

The in-process tests inject the sink; this one runs the *actual* plugin hook script exactly as
Claude Code invokes it — as a subprocess, with the PreToolUse payload on stdin and the plugin
environment set — against a real temporary git repo, then reads the branch sink back. This is
the closest CI can get to "a real Claude Code session produces EventRecords in the branch sink",
and it proves the whole shell → engine → branch-sink wiring plus the hook's fail-open posture.
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
HOOK_SCRIPT = REPO_ROOT / "plugins" / "claude-code" / "bin" / "pre-tool-use.sh"

# Drive the engine as a module so the test doesn't depend on the console script being on PATH.
ENGINE_COMMAND = f"{sys.executable} -m sailguarding.sensor"


def _init_repo(path: Path) -> None:
    def run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=path, capture_output=True, check=True)

    run("init", "-b", "trunk")
    run("config", "user.name", "test")
    run("config", "user.email", "test@localhost")
    run("commit", "--allow-empty", "-m", "initial")


def _payload(cwd: Path) -> bytes:
    return json.dumps(
        {
            "session_id": "e2e-session",
            "cwd": str(cwd),
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "checkout.py", "content": "print('hi')"},
        }
    ).encode()


def _invoke_hook(cwd: Path, *, payload: bytes, engine: str) -> subprocess.CompletedProcess[bytes]:
    env = {
        "PATH": _env_path(),
        "CLAUDE_PLUGIN_ROOT": str(HOOK_SCRIPT.parent.parent),
        "CLAUDE_PROJECT_DIR": str(cwd),
        "SAILGUARDING_ENGINE": engine,
        # Keep the module importable in the subprocess.
        "PYTHONPATH": str(REPO_ROOT / "src"),
    }
    return subprocess.run(
        [str(HOOK_SCRIPT)], input=payload, env=env, capture_output=True, cwd=str(cwd)
    )


def _env_path() -> str:
    import os

    return os.environ.get("PATH", "")


def test_real_hook_writes_event_to_branch_sink(tmp_path: Path) -> None:
    _init_repo(tmp_path)

    result = _invoke_hook(tmp_path, payload=_payload(tmp_path), engine=ENGINE_COMMAND)

    # Fail-open contract: exit 0 and nothing on stdout (no permission decision emitted).
    assert result.returncode == 0
    assert result.stdout == b""

    # The event landed in the branch sink, with the tool call and context captured.
    storage = BranchStorage(BranchStorageConfig(repo_path=tmp_path))
    records = storage.read_session("e2e-session")
    assert len(records) == 1
    (record,) = records
    assert record.tool_name == "Edit"
    assert record.tool_input == {"file_path": "checkout.py", "content": "print('hi')"}
    assert record.harness_id == "claude-code"
    assert record.context["repo"] == tmp_path.name
    assert record.context["git_branch"] == "trunk"
    assert record.context["git_commit"]


def test_real_hook_never_dirties_the_working_tree(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    branch_before = _git(tmp_path, "rev-parse", "--abbrev-ref", "HEAD")
    head_before = _git(tmp_path, "rev-parse", "HEAD")

    _invoke_hook(tmp_path, payload=_payload(tmp_path), engine=ENGINE_COMMAND)

    assert _git(tmp_path, "status", "--porcelain") == ""
    assert _git(tmp_path, "rev-parse", "--abbrev-ref", "HEAD") == branch_before
    assert _git(tmp_path, "rev-parse", "HEAD") == head_before


def test_real_hook_is_fail_open_when_the_engine_is_broken(tmp_path: Path) -> None:
    _init_repo(tmp_path)

    # A bogus engine command guarantees the engine invocation fails; the hook must still exit 0.
    result = _invoke_hook(tmp_path, payload=_payload(tmp_path), engine="this-engine-does-not-exist")

    assert result.returncode == 0
    assert result.stdout == b""


@pytest.fixture(autouse=True)
def _require_hook_script() -> None:
    if not HOOK_SCRIPT.exists():
        pytest.skip(f"hook script not found at {HOOK_SCRIPT}")


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True, text=True)
    return proc.stdout.strip()
