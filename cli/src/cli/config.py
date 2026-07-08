"""The ``sg config`` command group — edit the operator config the sensor reads.

The sensor resolves its settings from the environment, then this on-disk config file, then
built-in defaults (see :mod:`sailguarding.sensor.pluginconfig`). This group is the operator's
front door to that file: it reads and writes the *same* :class:`PluginConfig` schema the engine
reads, so the two can never drift. The headline setting is ``store`` — which data store the
sensor commits captured events to.

Every command takes the file path from the same resolver the engine uses, so ``sg config`` and a
running sensor always agree on *which* file is in play.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

import click

from sailguarding.sensor.pluginconfig import (
    FIELD_NAMES,
    VALID_STORES,
    ConfigError,
    PluginConfig,
    default_config_path,
    load,
    save,
)


def _env() -> Mapping[str, str]:
    return os.environ


def _path() -> Path:
    """The config file the engine would read for this environment."""
    return default_config_path(_env())


def _load() -> PluginConfig:
    try:
        return load(_path())
    except (ConfigError, ValueError) as exc:
        raise click.ClickException(f"{_path()}: {exc}") from exc


def _save(config: PluginConfig) -> None:
    path = _path()
    save(path, config)


def _render(config: PluginConfig, path: Path) -> str:
    """A human-readable snapshot of every field and where the file lives."""
    lines = [f"config file: {path}", ""]
    for key in FIELD_NAMES:
        value = config.get(key)
        if key == "redact_keys":
            shown = ", ".join(value) if value else "(unset)"
        else:
            shown = value if value is not None else "(unset)"
        lines.append(f"  {key} = {shown}")
    return "\n".join(lines)


@click.group(name="config")
def config() -> None:
    """Configure how the sensor plugin works — most importantly, which data store it uses."""


@config.command(name="path")
def path_cmd() -> None:
    """Print the path of the config file the sensor reads."""
    click.echo(str(_path()))


@config.command(name="show")
def show_cmd() -> None:
    """Show every setting and its current value (``(unset)`` falls through to the default)."""
    click.echo(_render(_load(), _path()))


@config.command(name="get")
@click.argument("key")
def get_cmd(key: str) -> None:
    """Print the value of a single KEY."""
    config_obj = _load()
    try:
        value = config_obj.get(key)
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc
    if key == "redact_keys":
        click.echo(", ".join(value))
    elif value is not None:
        click.echo(str(value))


@config.command(name="set")
@click.argument("key")
@click.argument("value")
def set_cmd(key: str, value: str) -> None:
    """Set KEY to VALUE (for ``redact_keys``, VALUE is a comma-separated list)."""
    try:
        updated = _load().set(key, value)
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc
    _save(updated)
    click.echo(f"Set {key} = {value} in {_path()}.")


@config.command(name="unset")
@click.argument("key")
def unset_cmd(key: str) -> None:
    """Clear KEY back to its built-in default."""
    try:
        updated = _load().unset(key)
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc
    _save(updated)
    click.echo(f"Unset {key} in {_path()}.")


@config.command(name="store")
@click.argument("name", type=click.Choice(VALID_STORES))
@click.option(
    "--path",
    "store_path",
    help="Directory for the filesystem store (absolute or repo-relative).",
)
@click.option("--branch", "branch", help="Events branch name for the branch store.")
def store_cmd(name: str, store_path: str | None, branch: str | None) -> None:
    """Select the data store NAME and, optionally, its path/branch in one step."""
    try:
        updated = _load().set("store", name)
        if store_path is not None:
            updated = updated.set("store_path", store_path)
        if branch is not None:
            updated = updated.set("branch", branch)
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc
    _save(updated)
    detail = f" (path {store_path})" if name == "filesystem" and store_path else ""
    click.echo(f"Store set to {name}{detail} in {_path()}.")
