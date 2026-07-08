"""The ``sg`` command group — Click wiring over :mod:`cli.plugin`.

Runnable as the ``sg`` console script or ``python -m cli``.
"""

from __future__ import annotations

from pathlib import Path

import click

from cli import plugin
from cli.config import config
from cli.plugin import PluginRef, require_claude, resolve_ref, subprocess_runner


def _ref() -> PluginRef:
    """Resolve the plugin reference from this source file's location, mapping errors to Click."""
    try:
        return resolve_ref(Path(__file__).resolve())
    except (FileNotFoundError, ValueError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="cli", prog_name="sg")
def sg() -> None:
    """sailguarding operator CLI — manage the Claude Code sensor plugin."""


@sg.command()
def install() -> None:
    """Register the local marketplace, then install and enable the sensor plugin."""
    require_claude()
    ref = _ref()
    plugin.install(ref, subprocess_runner)
    click.echo(f"Installed and enabled {ref.ref} (from {ref.repo_root}).")


@sg.command()
def enable() -> None:
    """Enable the sensor plugin (assumes it is already installed)."""
    require_claude()
    ref = _ref()
    plugin.enable(ref, subprocess_runner)
    click.echo(f"Enabled {ref.ref}.")


@sg.command()
def disable() -> None:
    """Disable and uninstall the plugin, and remove the local marketplace (no residue)."""
    require_claude()
    ref = _ref()
    plugin.disable(ref, subprocess_runner)
    click.echo(f"Disabled and removed {ref.ref}; no residue left.")


@sg.command()
def status() -> None:
    """Show the current marketplace and plugin state."""
    require_claude()
    ref = _ref()
    click.echo(plugin.status(ref, subprocess_runner))


sg.add_command(config)


if __name__ == "__main__":
    sg()
