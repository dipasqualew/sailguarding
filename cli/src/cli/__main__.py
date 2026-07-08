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
    """Resolve the plugin reference (repo checkout → marketplace manifest), mapping errors to Click.

    ``resolve_ref`` locates the checkout from ``$SAILGUARDING_REPO``, the working directory, or this
    source file — so it works whether ``sg`` was installed editable or copied into a tool venv.
    """
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
def update() -> None:
    """Refresh the local marketplace and update the sensor plugin to the latest version."""
    require_claude()
    ref = _ref()
    plugin.update(ref, subprocess_runner)
    click.echo(f"Updated {ref.ref} (from {ref.repo_root}).")


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


@sg.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Interface to bind.")
@click.option("--port", default=8000, show_default=True, type=int, help="Port to serve on.")
def serve(host: str, port: int) -> None:
    """Serve the dashboard — review the recorded tool calls and delegation scores in a browser."""
    from sailguarding.web.server import serve as serve_dashboard

    serve_dashboard(host, port)


# -- Sensor hook entrypoints -------------------------------------------------
#
# The plugin's hook (record on PreToolUse, flush on Stop/SessionEnd) shells into the engine, and
# `sg` is the *only* command the operator puts on PATH — so the sensor lives behind `sg` too,
# rather than a second `sailguarding` console script. These commands are hidden: they are called
# by the hook with the payload on stdin, not by humans. The engine itself is fail-open (it reads
# stdin, swallows every error, and exits 0), so nothing here can break the user's agent session.


def _run_sensor(command: str) -> None:
    from sailguarding.sensor.cli import main

    main([command])


@sg.command(hidden=True)
def record() -> None:
    """Sensor hook (PreToolUse): stage the tool call read from stdin. Called by the plugin."""
    _run_sensor("record")


@sg.command(hidden=True)
def flush() -> None:
    """Sensor hook (Stop/SessionEnd): commit the session's staged events. Called by the plugin."""
    _run_sensor("flush")


sg.add_command(config)


if __name__ == "__main__":
    sg()
