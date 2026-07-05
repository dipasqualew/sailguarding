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
HOOK_SCRIPT = PLUGIN_DIR / "bin" / "pre-tool-use.sh"


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text())
    return data


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


def test_hooks_declare_a_pre_tool_use_command_hook() -> None:
    hooks = _load(HOOKS_FILE)["hooks"]

    pre_tool_use = hooks["PreToolUse"]
    assert len(pre_tool_use) == 1
    matcher = pre_tool_use[0]
    # A catch-all matcher: the sensor records every tool call.
    assert matcher["matcher"] == "*"
    (hook,) = matcher["hooks"]
    assert hook["type"] == "command"
    # The command resolves its script from the plugin's install dir via CLAUDE_PLUGIN_ROOT.
    assert hook["command"] == "${CLAUDE_PLUGIN_ROOT}/bin/pre-tool-use.sh"


def test_hook_command_points_at_an_existing_executable_script() -> None:
    hook = _load(HOOKS_FILE)["hooks"]["PreToolUse"][0]["hooks"][0]
    relative = hook["command"].replace("${CLAUDE_PLUGIN_ROOT}/", "")

    script = PLUGIN_DIR / relative

    assert script == HOOK_SCRIPT
    assert script.exists()
    mode = script.stat().st_mode
    assert mode & stat.S_IXUSR, "hook script must be executable"


def test_hook_script_invokes_the_engine_record_entrypoint() -> None:
    body = HOOK_SCRIPT.read_text()

    # It shells into the configurable engine's `record` subcommand and is fail-open (exit 0).
    assert "SAILGUARDING_ENGINE" in body
    assert "record" in body
    assert "exit 0" in body


def test_manifest_and_marketplace_agree_on_the_plugin_name() -> None:
    manifest_name = _load(PLUGIN_MANIFEST)["name"]
    marketplace_entry = _load(MARKETPLACE)["plugins"][0]["name"]

    assert manifest_name == marketplace_entry


@pytest.mark.skipif(os.name == "nt", reason="POSIX shebang check")
def test_hook_script_has_a_shebang() -> None:
    assert HOOK_SCRIPT.read_text().startswith("#!")
