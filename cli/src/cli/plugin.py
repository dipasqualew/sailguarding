"""Plugin lifecycle, ported from ``scripts/plugin.sh``.

The logic here is a thin orchestration of Claude Code's own ``claude plugin`` flow — we do *not*
hand-edit ``~/.claude`` settings, so we never drift from Claude Code's internal schema. Every
action is idempotent: re-running ``install`` when already installed, or ``disable`` when already
gone, is a safe no-op.

The subprocess runner is injected (``Runner``) so the commands are testable without touching the
real ``claude`` CLI or the user's config.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

# A runner takes an argv and returns (exit_code, stdout). Injected so tests can stub `claude`.
Runner = Callable[[Sequence[str]], tuple[int, str]]

# The marker that identifies the repo root: the local marketplace manifest lives there.
MARKETPLACE_MANIFEST = Path(".claude-plugin") / "marketplace.json"


@dataclass(frozen=True)
class PluginRef:
    """Resolved identifiers for the local marketplace and the plugin it publishes."""

    repo_root: Path
    marketplace_name: str
    plugin_name: str

    @property
    def ref(self) -> str:
        """The ``plugin@marketplace`` reference Claude Code addresses the plugin by."""
        return f"{self.plugin_name}@{self.marketplace_name}"


def find_repo_root(start: Path) -> Path:
    """Walk up from ``start`` to the repo root (the dir holding the marketplace manifest).

    Because this package is installed *editable*, ``start`` (this file) lives inside the repo, so
    the walk resolves the same repo the source is edited in.
    """
    for candidate in (start, *start.parents):
        if (candidate / MARKETPLACE_MANIFEST).is_file():
            return candidate
    raise FileNotFoundError(
        f"could not locate {MARKETPLACE_MANIFEST} walking up from {start}; "
        "is the cli package still inside the sailguarding repo?"
    )


def resolve_ref(start: Path) -> PluginRef:
    """Read the local marketplace manifest and derive the plugin reference from it."""
    repo_root = find_repo_root(start)
    manifest = json.loads((repo_root / MARKETPLACE_MANIFEST).read_text())
    marketplace_name = manifest["name"]
    plugins = manifest.get("plugins") or []
    if not plugins:
        raise ValueError(f"{MARKETPLACE_MANIFEST} declares no plugins")
    plugin_name = plugins[0]["name"]
    return PluginRef(
        repo_root=repo_root,
        marketplace_name=marketplace_name,
        plugin_name=plugin_name,
    )


def subprocess_runner(argv: Sequence[str]) -> tuple[int, str]:
    """Default runner: invoke a command, capturing combined output."""
    proc = subprocess.run(
        list(argv),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def require_claude() -> None:
    """Fail early with a clear message if the ``claude`` CLI isn't on PATH."""
    if shutil.which("claude") is None:
        raise FileNotFoundError(
            "the 'claude' CLI is required but was not found on PATH. "
            "Install Claude Code, then re-run."
        )


def _claude(runner: Runner, *args: str) -> tuple[int, str]:
    return runner(("claude", "plugin", *args))


def ensure_marketplace(ref: PluginRef, runner: Runner) -> None:
    """Register the local marketplace if absent, or refresh it if already known."""
    code, out = _claude(runner, "marketplace", "list")
    if code == 0 and ref.marketplace_name in out:
        _claude(runner, "marketplace", "update", ref.marketplace_name)
    else:
        _claude(runner, "marketplace", "add", str(ref.repo_root))


def install(ref: PluginRef, runner: Runner) -> None:
    """Register the marketplace, then install + enable the plugin (all idempotent)."""
    ensure_marketplace(ref, runner)
    _claude(runner, "install", ref.ref, "--scope", "user")
    _claude(runner, "enable", ref.ref)


def enable(ref: PluginRef, runner: Runner) -> None:
    """Enable an already-installed plugin."""
    _claude(runner, "enable", ref.ref)


def disable(ref: PluginRef, runner: Runner) -> None:
    """Disable, uninstall, and drop the local marketplace — leaving no residue."""
    _claude(runner, "disable", ref.ref)
    _claude(runner, "uninstall", ref.ref)
    code, out = _claude(runner, "marketplace", "list")
    if code == 0 and ref.marketplace_name in out:
        _claude(runner, "marketplace", "remove", ref.marketplace_name)


def status(ref: PluginRef, runner: Runner) -> str:
    """Return a human-readable snapshot of marketplace + plugin state."""
    _, markets = _claude(runner, "marketplace", "list")
    _, plugins = _claude(runner, "list")
    return f"== Marketplaces ==\n{markets.strip()}\n\n== Plugins ==\n{plugins.strip()}"
