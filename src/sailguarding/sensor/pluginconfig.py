"""The persistent, operator-managed plugin config file.

The sensor's per-invocation settings (:class:`~sailguarding.sensor.config.SensorConfig`) can come
from three places, in precedence order: an environment variable, this config file, then a built-in
default. Environment variables stay highest so a one-off override still wins; this file is where an
operator's *durable* choices live — most importantly **which data store the sensor commits to**.

The file is plain JSON so the zero-dependency engine can read it and the ``sg`` CLI can write it,
sharing this one schema so the two can't drift. It is versioned (``schema_version``) and
round-trips: ``PluginConfig.from_dict(c.to_dict()) == c``. Every field is optional — an absent key
means "fall through to the sensor's default", so a fresh install with no file behaves exactly as
before this file existed.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

# Bumped only on an incompatible change to the on-disk shape; a reader refuses versions it does
# not understand rather than silently misreading them.
CONFIG_SCHEMA_VERSION = 1

# Override for the config file location; else it lives under the XDG config home.
ENV_CONFIG_PATH = "SAILGUARDING_CONFIG"
ENV_XDG_CONFIG_HOME = "XDG_CONFIG_HOME"

# The data-store backends the sensor can commit to. ``branch`` is the git-native default;
# ``filesystem`` writes plain JSONL under a directory (for non-git repos or a shared location).
VALID_STORES = ("branch", "filesystem")

# The keys an operator may set, in a stable display order. ``store`` selects the backend; the
# rest tune it or the capture (branch name, filesystem directory, ambient labels, extra secrets).
FIELD_NAMES = ("store", "branch", "store_path", "team", "environment", "redact_keys")


class ConfigError(ValueError):
    """A config value is unknown or invalid — raised for the CLI to render cleanly."""


@dataclass(frozen=True)
class PluginConfig:
    """Durable, operator-set overrides for the sensor. Every field is optional.

    :param store: Which data store the sensor commits to (``branch`` or ``filesystem``).
    :param branch: Events branch name, when the store is ``branch``.
    :param store_path: Directory the JSONL log is written under, when the store is ``filesystem``.
    :param team: Ambient team label stamped on captured context.
    :param environment: Ambient environment label stamped on captured context.
    :param redact_keys: Extra secret-bearing key patterns, added to the built-in defaults.
    """

    store: str | None = None
    branch: str | None = None
    store_path: str | None = None
    team: str | None = None
    environment: str | None = None
    redact_keys: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """A JSON-ready dict of only the keys actually set, plus the schema version."""
        data: dict[str, Any] = {"schema_version": CONFIG_SCHEMA_VERSION}
        if self.store is not None:
            data["store"] = self.store
        if self.branch is not None:
            data["branch"] = self.branch
        if self.store_path is not None:
            data["store_path"] = self.store_path
        if self.team is not None:
            data["team"] = self.team
        if self.environment is not None:
            data["environment"] = self.environment
        if self.redact_keys:
            data["redact_keys"] = list(self.redact_keys)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PluginConfig:
        """Rebuild from a dict produced by :meth:`to_dict`, validating the schema version."""
        version = data.get("schema_version", CONFIG_SCHEMA_VERSION)
        if version != CONFIG_SCHEMA_VERSION:
            raise ConfigError(
                f"unsupported config schema_version {version!r}; "
                f"this build reads version {CONFIG_SCHEMA_VERSION}"
            )
        store = data.get("store")
        if store is not None:
            _validate_store(store)
        return cls(
            store=store,
            branch=data.get("branch"),
            store_path=data.get("store_path"),
            team=data.get("team"),
            environment=data.get("environment"),
            redact_keys=tuple(data.get("redact_keys") or ()),
        )

    # -- editing (the CLI's set/get/unset) --------------------------------------

    def get(self, key: str) -> Any:
        """Return the current value of ``key`` (``None`` / ``()`` if unset)."""
        _require_key(key)
        return getattr(self, key)

    def set(self, key: str, raw: str) -> PluginConfig:
        """Return a copy with ``key`` set from the string ``raw``, validating where needed."""
        _require_key(key)
        if key == "redact_keys":
            value: Any = _split_csv(raw)
        elif key == "store":
            _validate_store(raw)
            value = raw
        else:
            value = raw
        return replace(self, **{key: value})

    def unset(self, key: str) -> PluginConfig:
        """Return a copy with ``key`` cleared back to its unset default."""
        _require_key(key)
        default: Any = () if key == "redact_keys" else None
        return replace(self, **{key: default})


def default_config_path(env: Mapping[str, str]) -> Path:
    """Where the config file lives: ``$SAILGUARDING_CONFIG`` else under the XDG config home."""
    override = env.get(ENV_CONFIG_PATH)
    if override:
        return Path(override)
    xdg = env.get(ENV_XDG_CONFIG_HOME)
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "sailguarding" / "config.json"


def load(path: Path) -> PluginConfig:
    """Read the config at ``path``; a missing file is an empty (all-default) config."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return PluginConfig()
    return PluginConfig.from_dict(json.loads(text))


def save(path: Path, config: PluginConfig) -> None:
    """Write ``config`` to ``path`` as pretty, sorted JSON, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(config.to_dict(), sort_keys=True, indent=2, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")


def load_from_env(env: Mapping[str, str]) -> PluginConfig:
    """Load the config from the location :func:`default_config_path` resolves for ``env``."""
    return load(default_config_path(env))


def _require_key(key: str) -> None:
    if key not in FIELD_NAMES:
        raise ConfigError(f"unknown config key {key!r}; valid keys: {', '.join(FIELD_NAMES)}")


def _validate_store(store: str) -> None:
    if store not in VALID_STORES:
        raise ConfigError(f"unknown store {store!r}; valid stores: {', '.join(VALID_STORES)}")


def _split_csv(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())
