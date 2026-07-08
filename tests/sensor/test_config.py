"""Unit tests for :mod:`sailguarding.sensor.config` resolution and store dispatch.

``SensorConfig.resolve`` layers three sources — environment over the operator config file over a
built-in default — into one immutable config; ``build_commit_storage`` picks the commit sink from
the resolved ``store``; ``resolve_store_root`` derives where the filesystem store writes. Each is
tested as a pure function with its inputs injected: ``env`` dicts, a :class:`PluginConfig`, and a
fake :class:`GitRunner` — no real git, no environment mutation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from sailguarding.sensor.config import (
    DEFAULT_BRANCH,
    DEFAULT_STORE,
    SensorConfig,
    build_commit_storage,
    resolve_store_root,
)
from sailguarding.sensor.pluginconfig import ConfigError, PluginConfig
from sailguarding.sensor.redaction import DEFAULT_SECRET_KEY_PATTERNS
from sailguarding.storage import BranchStorage, FilesystemStorage
from sailguarding.storage.git import GitResult

REPO = Path("/work/checkout")


class StubGit:
    """A :class:`GitRunner` answering ``rev-parse --absolute-git-dir`` with a fixed result."""

    def __init__(self, result: GitResult) -> None:
        self._result = result

    def __call__(
        self,
        args: Sequence[str],
        *,
        stdin: bytes | None = None,
        env: Mapping[str, str] | None = None,
    ) -> GitResult:
        return self._result


def _ok(stdout: str) -> GitResult:
    return GitResult(returncode=0, stdout=stdout.encode(), stderr=b"")


def _fail() -> GitResult:
    return GitResult(returncode=128, stdout=b"", stderr=b"not a git repository\n")


# -- SensorConfig.resolve: precedence ---------------------------------------------


def test_resolve_with_nothing_set_uses_defaults() -> None:
    config = SensorConfig.resolve(REPO, {}, PluginConfig())

    assert config.store == DEFAULT_STORE
    assert config.branch == DEFAULT_BRANCH
    assert config.team is None
    assert config.environment is None
    assert config.store_path is None
    assert config.redact_keys == DEFAULT_SECRET_KEY_PATTERNS


def test_resolve_file_config_beats_default() -> None:
    file_config = PluginConfig(
        store="filesystem", branch="team/events", team="core", environment="staging"
    )

    config = SensorConfig.resolve(REPO, {}, file_config)

    assert config.store == "filesystem"
    assert config.branch == "team/events"
    assert config.team == "core"
    assert config.environment == "staging"


@pytest.mark.parametrize(
    ("env_var", "attr", "value"),
    [
        pytest.param("SAILGUARDING_STORE", "store", "filesystem", id="store"),
        pytest.param("SAILGUARDING_BRANCH", "branch", "env/events", id="branch"),
        pytest.param("SAILGUARDING_TEAM", "team", "env-team", id="team"),
        pytest.param("SAILGUARDING_ENVIRONMENT", "environment", "env-env", id="environment"),
    ],
)
def test_resolve_env_beats_file_config(env_var: str, attr: str, value: str) -> None:
    file_config = PluginConfig(
        store="branch", branch="file/events", team="file-team", environment="file-env"
    )

    config = SensorConfig.resolve(REPO, {env_var: value}, file_config)

    assert getattr(config, attr) == value


def test_resolve_store_path_from_env_beats_file_and_expands_user() -> None:
    file_config = PluginConfig(store="filesystem", store_path="/file/path")

    config = SensorConfig.resolve(REPO, {"SAILGUARDING_STORE_PATH": "~/env/path"}, file_config)

    assert config.store_path == Path("~/env/path").expanduser()


def test_resolve_store_path_from_file_when_env_absent() -> None:
    config = SensorConfig.resolve(
        REPO, {}, PluginConfig(store="filesystem", store_path="/file/path")
    )

    assert config.store_path == Path("/file/path")


def test_resolve_redact_keys_concatenate_defaults_env_and_file() -> None:
    file_config = PluginConfig(redact_keys=("file_key",))

    config = SensorConfig.resolve(REPO, {"SAILGUARDING_REDACT_KEYS": "env_a, env_b"}, file_config)

    assert config.redact_keys == (*DEFAULT_SECRET_KEY_PATTERNS, "env_a", "env_b", "file_key")


def test_resolve_invalid_store_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="unknown store"):
        SensorConfig.resolve(REPO, {"SAILGUARDING_STORE": "redis"}, PluginConfig())


# -- build_commit_storage: dispatch -----------------------------------------------


def test_build_commit_storage_returns_branch_storage_by_default() -> None:
    config = SensorConfig(repo_path=REPO)

    storage = build_commit_storage(config)

    assert isinstance(storage, BranchStorage)


def test_build_commit_storage_returns_filesystem_storage_when_selected() -> None:
    config = SensorConfig(repo_path=REPO, store="filesystem", store_path=Path("/data/sg"))

    storage = build_commit_storage(config)

    assert isinstance(storage, FilesystemStorage)


def test_build_commit_storage_filesystem_without_path_raises() -> None:
    config = SensorConfig(repo_path=REPO, store="filesystem", store_path=None)

    with pytest.raises(ValueError, match="store_path"):
        build_commit_storage(config)


# -- resolve_store_root -----------------------------------------------------------


def test_resolve_store_root_honours_absolute_configured_path() -> None:
    root = resolve_store_root(StubGit(_fail()), REPO, Path("/shared/mount/sg"))

    assert root == Path("/shared/mount/sg")


def test_resolve_store_root_takes_relative_configured_path_against_repo() -> None:
    root = resolve_store_root(StubGit(_fail()), REPO, Path("logs/sg"))

    assert root == REPO / "logs/sg"


def test_resolve_store_root_defaults_under_git_dir() -> None:
    git = StubGit(_ok("/work/checkout/.git\n"))

    root = resolve_store_root(git, REPO, None)

    assert root == Path("/work/checkout/.git/sailguarding/events")


def test_resolve_store_root_falls_back_to_dotdir_without_git() -> None:
    root = resolve_store_root(StubGit(_fail()), REPO, None)

    assert root == REPO / ".sailguarding" / "events"
