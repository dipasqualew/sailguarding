"""Tests for the engine-backed ``sg`` commands: the sensor hooks and ``sg serve``.

``sg`` is the one command the operator puts on PATH, so the sensor and the dashboard both live
behind it. These assert the *delegation seams* without running the real engine or binding a socket:

- ``sg record`` / ``sg flush`` — the plugin hook's PreToolUse / Stop roles forward to the engine's
  fail-open ``main`` with the matching argv, and are hidden from ``sg --help`` (the hook calls them,
  not humans). Their record/flush behaviour proper is covered in ``tests/sensor/``.
- ``sg serve`` — the dashboard front door forwards host/port to ``web.server.serve``, and *is*
  visible in ``sg --help``.
"""

from __future__ import annotations

import re

import pytest
from click.testing import CliRunner

from cli.__main__ import sg


def _listed_commands(help_text: str) -> set[str]:
    """The command/option names `--help` actually lists (first token of each indented entry)."""
    return set(re.findall(r"^\s{2,}(\S+)", help_text, re.MULTILINE))


@pytest.fixture
def engine_calls(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Capture the argv each ``sg`` sensor command forwards to the engine, without running it."""
    recorded: list[list[str]] = []

    def _fake_main(argv: list[str]) -> int:
        recorded.append(argv)
        return 0

    # The command imports ``main`` lazily, so patch it on the engine module it resolves at call.
    monkeypatch.setattr("sailguarding.sensor.cli.main", _fake_main)
    return recorded


@pytest.mark.parametrize("command", ["record", "flush"])
def test_command_delegates_to_the_engine_with_matching_argv(
    command: str, engine_calls: list[list[str]]
) -> None:
    result = CliRunner().invoke(sg, [command])

    assert result.exit_code == 0
    assert engine_calls == [[command]]


def test_sensor_commands_are_hidden_from_the_operator_help() -> None:
    # They are hook plumbing, not operator commands, so they must not be listed in `sg --help`.
    listed = _listed_commands(CliRunner().invoke(sg, ["--help"]).output)

    assert "record" not in listed
    assert "flush" not in listed


def test_serve_delegates_to_the_dashboard_server(monkeypatch: pytest.MonkeyPatch) -> None:
    # `sg serve` is the front door to the dashboard; assert it starts the server on the given
    # host/port without actually binding a socket.
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "sailguarding.web.server.serve", lambda host, port: calls.append((host, port))
    )

    result = CliRunner().invoke(sg, ["serve", "--host", "0.0.0.0", "--port", "9137"])

    assert result.exit_code == 0
    assert calls == [("0.0.0.0", 9137)]


def test_serve_is_a_visible_operator_command() -> None:
    # Unlike the hook plumbing, `serve` is for humans — it must show up in `sg --help`.
    assert "serve" in _listed_commands(CliRunner().invoke(sg, ["--help"]).output)
