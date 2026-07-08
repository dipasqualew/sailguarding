"""Structural checks on the plugin and local marketplace so their wiring can't rot.

A live Claude Code session can't run in CI, so the acceptance criterion "installs through the
in-repo marketplace" is guarded here at the structural level: the marketplace lists the plugin
at the right relative source, the plugin manifest and hooks are well-formed, the hook points at
a script that actually exists and is executable, and the whole chain (marketplace → plugin →
hook → engine command) hangs together.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"
PLUGIN_DIR = REPO_ROOT / "plugins" / "claude-code"
PLUGIN_MANIFEST = PLUGIN_DIR / ".claude-plugin" / "plugin.json"
HOOKS_FILE = PLUGIN_DIR / "hooks" / "hooks.json"
HOOK_SCRIPT = PLUGIN_DIR / "bin" / "hook.sh"


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text())
    return data


def _sole_command(hooks: dict[str, Any], event: str) -> str:
    groups = hooks[event]
    assert len(groups) == 1
    (hook,) = groups[0]["hooks"]
    assert hook["type"] == "command"
    command: str = hook["command"]
    return command


def test_marketplace_lists_the_plugin_at_a_relative_source() -> None:
    marketplace = _load(MARKETPLACE)

    assert marketplace["name"] == "sailguarding-local"
    assert marketplace["owner"]["name"]
    (entry,) = marketplace["plugins"]
    assert entry["name"] == "sailguarding"
    # A local, in-repo source: a relative path starting with "./", resolved from the repo root.
    assert entry["source"] == "./plugins/claude-code"
    assert (REPO_ROOT / entry["source"]).resolve() == PLUGIN_DIR.resolve()


def test_plugin_manifest_has_required_fields() -> None:
    manifest = _load(PLUGIN_MANIFEST)

    assert manifest["name"] == "sailguarding"
    assert manifest["description"]
    assert manifest["version"]


def test_pre_tool_use_records_every_tool_call() -> None:
    hooks = _load(HOOKS_FILE)["hooks"]

    matcher = hooks["PreToolUse"][0]
    # A catch-all matcher: the sensor records every tool call.
    assert matcher["matcher"] == "*"
    # The command resolves its script from the plugin's install dir via CLAUDE_PLUGIN_ROOT, and
    # invokes the engine's `record` subcommand (stage the tool call).
    assert _sole_command(hooks, "PreToolUse") == "${CLAUDE_PLUGIN_ROOT}/bin/hook.sh record"


def test_stop_and_session_end_flush_the_session() -> None:
    hooks = _load(HOOKS_FILE)["hooks"]

    # Both lifecycle events commit the staged events via the engine's `flush` subcommand: Stop
    # once per turn, SessionEnd once per session (the backstop).
    assert _sole_command(hooks, "Stop") == "${CLAUDE_PLUGIN_ROOT}/bin/hook.sh flush"
    assert _sole_command(hooks, "SessionEnd") == "${CLAUDE_PLUGIN_ROOT}/bin/hook.sh flush"


def test_every_hook_command_points_at_the_existing_executable_script() -> None:
    hooks = _load(HOOKS_FILE)["hooks"]

    for event in ("PreToolUse", "Stop", "SessionEnd"):
        command = _sole_command(hooks, event)
        relative = command.replace("${CLAUDE_PLUGIN_ROOT}/", "").split(" ", 1)[0]
        script = PLUGIN_DIR / relative
        assert script == HOOK_SCRIPT
        assert script.exists()
        assert script.stat().st_mode & stat.S_IXUSR, "hook script must be executable"


def test_hook_script_invokes_the_configurable_engine_and_is_fail_open() -> None:
    body = HOOK_SCRIPT.read_text()

    # It shells into the configurable engine's subcommand ($1) and is fail-open (exit 0).
    assert "SAILGUARDING_ENGINE" in body
    assert "subcommand" in body
    assert "exit 0" in body


def test_hook_script_defaults_to_resolving_the_sg_command() -> None:
    body = HOOK_SCRIPT.read_text()

    # `sg` is the one command on PATH; the hook must resolve it itself (Claude Code's GUI/login
    # PATH may hide the user's bin dir), so it looks it up on PATH and then under ~/.local/bin.
    assert "command -v sg" in body
    assert ".local/bin/sg" in body


def test_manifest_and_marketplace_agree_on_the_plugin_name() -> None:
    manifest_name = _load(PLUGIN_MANIFEST)["name"]
    marketplace_entry = _load(MARKETPLACE)["plugins"][0]["name"]

    assert manifest_name == marketplace_entry


@pytest.mark.skipif(os.name == "nt", reason="POSIX shebang check")
def test_hook_script_has_a_shebang() -> None:
    assert HOOK_SCRIPT.read_text().startswith("#!")
