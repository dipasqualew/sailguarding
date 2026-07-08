"""Unit tests for :mod:`sailguarding.sensor.pluginconfig`.

The operator config file is the durable, shared-schema seam between the ``sg config`` CLI and the
engine, so its contract is exercised as a pure value type: canonical round-trips, the CLI's
set/get/unset editing, path resolution from an injected ``env`` (never the real ``$HOME``/env), and
a missing file reading back as an empty config. Every case injects its inputs — an ``env`` dict, a
``tmp_path`` — and leaves the environment pristine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sailguarding.sensor.pluginconfig import (
    CONFIG_SCHEMA_VERSION,
    ConfigError,
    PluginConfig,
    default_config_path,
    load,
    load_from_env,
    save,
)


@pytest.mark.parametrize(
    "config",
    [
        pytest.param(PluginConfig(), id="empty"),
        pytest.param(PluginConfig(store="branch", branch="team/events"), id="branch"),
        pytest.param(
            PluginConfig(store="filesystem", store_path="/var/log/sg"), id="filesystem-path"
        ),
        pytest.param(PluginConfig(team="core", environment="staging"), id="ambient-labels"),
        pytest.param(PluginConfig(redact_keys=("token", "secret", "api_key")), id="redact-keys"),
        pytest.param(
            PluginConfig(
                store="filesystem",
                branch="team/events",
                store_path="~/sg",
                team="core",
                environment="prod",
                redact_keys=("token",),
            ),
            id="every-field",
        ),
    ],
)
def test_to_dict_from_dict_round_trips(config: PluginConfig) -> None:
    assert PluginConfig.from_dict(config.to_dict()) == config


def test_to_dict_carries_schema_version_and_omits_unset_keys() -> None:
    data = PluginConfig(store="filesystem").to_dict()

    assert data["schema_version"] == CONFIG_SCHEMA_VERSION
    assert data == {"schema_version": CONFIG_SCHEMA_VERSION, "store": "filesystem"}


def test_from_dict_without_schema_version_assumes_current() -> None:
    assert PluginConfig.from_dict({"store": "branch"}) == PluginConfig(store="branch")


@pytest.mark.parametrize(
    ("key", "raw", "expected"),
    [
        pytest.param("store", "filesystem", "filesystem", id="store"),
        pytest.param("branch", "team/events", "team/events", id="branch"),
        pytest.param("store_path", "/data/sg", "/data/sg", id="store-path"),
        pytest.param("team", "core", "core", id="team"),
        pytest.param("environment", "prod", "prod", id="environment"),
    ],
)
def test_set_then_get_returns_scalar_value(key: str, raw: str, expected: str) -> None:
    updated = PluginConfig().set(key, raw)

    assert updated.get(key) == expected


def test_set_redact_keys_parses_and_trims_csv() -> None:
    updated = PluginConfig().set("redact_keys", "a, b ,c")

    assert updated.get("redact_keys") == ("a", "b", "c")


def test_set_redact_keys_drops_empty_entries() -> None:
    updated = PluginConfig().set("redact_keys", "a, ,,b,")

    assert updated.get("redact_keys") == ("a", "b")


def test_unset_scalar_clears_to_none() -> None:
    config = PluginConfig(store="filesystem")

    assert config.unset("store").get("store") is None


def test_unset_redact_keys_clears_to_empty_tuple() -> None:
    config = PluginConfig(redact_keys=("token",))

    assert config.unset("redact_keys").get("redact_keys") == ()


def test_set_is_a_copy_leaving_the_original_untouched() -> None:
    original = PluginConfig()

    original.set("store", "filesystem")

    assert original.store is None


@pytest.mark.parametrize("method", ["get", "unset"])
def test_unknown_key_raises_config_error(method: str) -> None:
    with pytest.raises(ConfigError, match="unknown config key"):
        getattr(PluginConfig(), method)("nope")


def test_set_unknown_key_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="unknown config key"):
        PluginConfig().set("nope", "x")


def test_set_unknown_store_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="unknown store"):
        PluginConfig().set("store", "redis")


def test_from_dict_unknown_store_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="unknown store"):
        PluginConfig.from_dict({"store": "redis"})


def test_from_dict_unsupported_schema_version_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="schema_version"):
        PluginConfig.from_dict({"schema_version": CONFIG_SCHEMA_VERSION + 1})


def test_default_config_path_prefers_explicit_override() -> None:
    env = {
        "SAILGUARDING_CONFIG": "/etc/sg/config.json",
        "XDG_CONFIG_HOME": "/ignored",
    }

    assert default_config_path(env) == Path("/etc/sg/config.json")


def test_default_config_path_uses_xdg_config_home() -> None:
    env = {"XDG_CONFIG_HOME": "/home/dev/.xdg"}

    assert default_config_path(env) == Path("/home/dev/.xdg/sailguarding/config.json")


def test_default_config_path_falls_back_to_home_config() -> None:
    path = default_config_path({})

    assert path.parts[-3:] == (".config", "sailguarding", "config.json")


def test_load_missing_file_returns_empty_config(tmp_path: Path) -> None:
    assert load(tmp_path / "does-not-exist.json") == PluginConfig()


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    config = PluginConfig(store="filesystem", store_path="/data/sg", redact_keys=("token",))
    path = tmp_path / "nested" / "config.json"

    save(path, config)

    assert load(path) == config


def test_save_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "config.json"

    save(path, PluginConfig(store="branch"))

    assert path.exists()


def test_load_from_env_reads_the_resolved_path(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    config = PluginConfig(store="filesystem", store_path="/data/sg")
    save(path, config)

    assert load_from_env({"SAILGUARDING_CONFIG": str(path)}) == config
