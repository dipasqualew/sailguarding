"""Tests for the ``sg config`` command group.

``sg config`` is the operator's front door to the config file the sensor reads. These drive it
through Click's :class:`CliRunner` against a config file in ``tmp_path`` (via the
``SAILGUARDING_CONFIG`` env var, so the developer's real ``~/.config`` is never touched), asserting
the observable CLI behaviour: the file path it resolves, that edits round-trip through
``show``/``get``, the ``store`` convenience, and that bad keys/stores fail with a non-zero exit.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from cli.config import config


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Where the CLI will read/write the operator config for a test."""
    return tmp_path / "sailguarding" / "config.json"


@pytest.fixture
def run(config_path: Path) -> Callable[..., Result]:
    """Invoke ``sg config`` with the config file pinned at ``config_path``."""
    runner = CliRunner()

    def _run(*args: str) -> Result:
        return runner.invoke(config, list(args), env={"SAILGUARDING_CONFIG": str(config_path)})

    return _run


def _stored(config_path: Path) -> dict[str, object]:
    return json.loads(config_path.read_text())  # type: ignore[no-any-return]


def test_path_prints_the_resolved_config_file(
    run: Callable[..., Result], config_path: Path
) -> None:
    result = run("path")

    assert result.exit_code == 0
    assert result.output.strip() == str(config_path)


def test_show_on_a_missing_file_lists_every_key_as_unset(run: Callable[..., Result]) -> None:
    result = run("show")

    assert result.exit_code == 0
    for key in ("store", "branch", "store_path", "team", "environment", "redact_keys"):
        assert f"{key} = (unset)" in result.output


def test_set_then_get_round_trips_a_value(run: Callable[..., Result]) -> None:
    assert run("set", "team", "payments").exit_code == 0

    result = run("get", "team")

    assert result.exit_code == 0
    assert result.output.strip() == "payments"


def test_set_store_is_reflected_in_show_and_written_to_disk(
    run: Callable[..., Result], config_path: Path
) -> None:
    assert run("set", "store", "filesystem").exit_code == 0

    assert "store = filesystem" in run("show").output
    assert _stored(config_path)["store"] == "filesystem"


def test_store_convenience_sets_backend_and_path_together(
    run: Callable[..., Result], config_path: Path
) -> None:
    result = run("store", "filesystem", "--path", "/data/sg-events")

    assert result.exit_code == 0
    stored = _stored(config_path)
    assert stored["store"] == "filesystem"
    assert stored["store_path"] == "/data/sg-events"


def test_redact_keys_are_parsed_from_a_comma_separated_list(
    run: Callable[..., Result],
) -> None:
    assert run("set", "redact_keys", "api_key, secret ,token").exit_code == 0

    result = run("get", "redact_keys")

    assert result.output.strip() == "api_key, secret, token"


def test_unset_clears_a_previously_set_key(run: Callable[..., Result], config_path: Path) -> None:
    run("set", "team", "payments")

    assert run("unset", "team").exit_code == 0
    assert "team = (unset)" in run("show").output
    assert "team" not in _stored(config_path)


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        pytest.param(("set", "nonsense", "x"), "unknown config key", id="unknown-key"),
        pytest.param(("set", "store", "redis"), "unknown store", id="unknown-store"),
        pytest.param(("get", "nonsense"), "unknown config key", id="unknown-key-get"),
        pytest.param(("store", "redis"), None, id="invalid-store-choice"),
    ],
)
def test_invalid_input_fails_with_nonzero_exit(
    run: Callable[..., Result], args: Sequence[str], expected: str | None
) -> None:
    result = run(*args)

    assert result.exit_code != 0
    if expected is not None:
        assert expected in result.output


def test_a_bad_edit_never_writes_the_config_file(
    run: Callable[..., Result], config_path: Path
) -> None:
    run("set", "store", "redis")

    assert not config_path.exists()
