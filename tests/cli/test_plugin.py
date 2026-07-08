"""Tests for :mod:`cli.plugin` — repo-root discovery and the ``claude plugin`` orchestration.

The headline case is discovery: ``sg`` is installed on PATH (often copied into an isolated tool
venv by ``uv tool install``), so the plugin *must not* assume its own source lives inside the
sailguarding checkout. These assert the working directory and ``$SAILGUARDING_REPO`` anchor the
walk, with the source file only a fallback — and that each lifecycle command drives ``claude`` with
the right argv, using an injected runner so nothing touches the real CLI.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from cli import plugin
from cli.plugin import (
    MARKETPLACE_MANIFEST,
    REPO_ENV_VAR,
    PluginRef,
    candidate_starts,
    find_repo_root,
    resolve_ref,
)


def _make_repo(
    root: Path, *, marketplace: str = "sailguarding-local", plugin_name: str = "sailguarding"
) -> Path:
    """Write a minimal local marketplace manifest under ``root`` and return ``root``."""
    manifest = root / MARKETPLACE_MANIFEST
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "name": marketplace,
                "plugins": [{"name": plugin_name, "source": "./plugins/claude-code"}],
            }
        )
    )
    return root


class FakeRunner:
    """Records each argv it is handed and replays a scripted response per command."""

    def __init__(self, responses: dict[tuple[str, ...], tuple[int, str]] | None = None) -> None:
        self.calls: list[list[str]] = []
        self._responses = responses or {}

    def __call__(self, argv: Sequence[str]) -> tuple[int, str]:
        argv = list(argv)
        self.calls.append(argv)
        return self._responses.get(tuple(argv), (0, ""))


# -- Repo-root discovery -----------------------------------------------------


def test_find_repo_root_walks_up_from_a_nested_start(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "checkout")
    nested = repo / "cli" / "src" / "cli"
    nested.mkdir(parents=True)

    assert find_repo_root(nested) == repo


def test_find_repo_root_reports_every_start_it_searched(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()

    with pytest.raises(FileNotFoundError) as excinfo:
        find_repo_root([a, b])

    message = str(excinfo.value)
    assert str(a) in message
    assert str(b) in message
    assert REPO_ENV_VAR in message  # points the operator at the escape hatch


def test_candidate_starts_prefers_env_override_then_cwd_then_source(tmp_path: Path) -> None:
    override = tmp_path / "named-checkout"
    source = tmp_path / "toolvenv" / "cli" / "__main__.py"

    starts = candidate_starts(source, env={REPO_ENV_VAR: str(override)})

    assert starts[0] == override
    assert starts[1] == Path.cwd()
    assert starts[2] == source


def test_candidate_starts_omits_override_when_unset(tmp_path: Path) -> None:
    source = tmp_path / "cli" / "__main__.py"

    starts = candidate_starts(source, env={})

    assert starts == [Path.cwd(), source]


def test_resolve_ref_finds_the_repo_from_the_working_directory_not_the_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The install scenario that used to fail: source outside the checkout, cwd inside it."""
    repo = _make_repo(tmp_path / "checkout")
    # Simulate `uv tool install ./cli`: the source is copied into a venv far from the repo.
    source = tmp_path / "toolvenv" / "site-packages" / "cli" / "__main__.py"
    source.parent.mkdir(parents=True)
    source.touch()
    # The operator runs `sg install` from within their checkout — no env override in play.
    monkeypatch.chdir(repo)

    ref = resolve_ref(source, env={})

    assert ref == PluginRef(
        repo_root=repo.resolve(), marketplace_name="sailguarding-local", plugin_name="sailguarding"
    )
    assert ref.ref == "sailguarding@sailguarding-local"


def test_resolve_ref_rejects_a_manifest_with_no_plugins(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    (repo / MARKETPLACE_MANIFEST).parent.mkdir(parents=True)
    (repo / MARKETPLACE_MANIFEST).write_text(json.dumps({"name": "empty", "plugins": []}))

    # Pin discovery to this repo via the override so the real checkout (cwd) can't win.
    with pytest.raises(ValueError, match="declares no plugins"):
        resolve_ref(repo / "cli", env={REPO_ENV_VAR: str(repo)})


# -- Lifecycle orchestration -------------------------------------------------


@pytest.fixture
def ref(tmp_path: Path) -> PluginRef:
    return PluginRef(
        repo_root=tmp_path / "checkout",
        marketplace_name="sailguarding-local",
        plugin_name="sailguarding",
    )


def test_install_registers_marketplace_then_installs_and_enables(ref: PluginRef) -> None:
    runner = FakeRunner()

    plugin.install(ref, runner)

    assert runner.calls == [
        ["claude", "plugin", "marketplace", "list"],
        ["claude", "plugin", "marketplace", "add", str(ref.repo_root)],
        ["claude", "plugin", "install", ref.ref, "--scope", "user"],
        ["claude", "plugin", "enable", ref.ref],
    ]


def test_update_refreshes_a_known_marketplace_then_updates_the_plugin(ref: PluginRef) -> None:
    # Marketplace already registered, so `ensure_marketplace` updates rather than adds it.
    runner = FakeRunner({("claude", "plugin", "marketplace", "list"): (0, ref.marketplace_name)})

    plugin.update(ref, runner)

    assert runner.calls == [
        ["claude", "plugin", "marketplace", "list"],
        ["claude", "plugin", "marketplace", "update", ref.marketplace_name],
        ["claude", "plugin", "update", ref.ref],
    ]


def test_update_adds_the_marketplace_first_when_it_is_absent(ref: PluginRef) -> None:
    runner = FakeRunner()  # marketplace list comes back empty

    plugin.update(ref, runner)

    assert runner.calls == [
        ["claude", "plugin", "marketplace", "list"],
        ["claude", "plugin", "marketplace", "add", str(ref.repo_root)],
        ["claude", "plugin", "update", ref.ref],
    ]
