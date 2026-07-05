"""The engine entrypoint's fail-open boundary and its silence on stdout.

The entrypoint must always exit 0 and never write to stdout — Claude Code reads "exit 0 + no
stdout" as "no decision, proceed normally". Anything printed to stdout risks being read as a
permission decision, so a sensor stays silent there and logs only to stderr.
"""

from __future__ import annotations

import io

import pytest

from sailguarding.sensor.cli import main
from sailguarding.sensor.mock import FrozenGit
from sailguarding.storage import InMemoryStorage


def _stdin(raw: bytes) -> io.BytesIO:
    return io.BytesIO(raw)


def _valid_payload_bytes() -> bytes:
    return (
        b'{"session_id":"s","cwd":"/work/checkout","hook_event_name":"PreToolUse",'
        b'"tool_name":"Edit","tool_input":{"file_path":"a.py"}}'
    )


def test_records_and_returns_zero_and_writes_no_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sink = InMemoryStorage()
    git = FrozenGit(toplevel="/work/checkout", branch="main", commit="c0ffee")

    code = main(
        ["record"],
        stdin=_stdin(_valid_payload_bytes()),
        env={},
        storage_factory=lambda _cfg: sink,
        git_factory=lambda _p: git,
    )

    assert code == 0
    assert len(sink.scan()) == 1
    assert capsys.readouterr().out == ""  # silence on stdout is load-bearing


def test_malformed_json_is_swallowed(capsys: pytest.CaptureFixture[str]) -> None:
    sink = InMemoryStorage()

    code = main(
        ["record"],
        stdin=_stdin(b"not json at all"),
        env={},
        storage_factory=lambda _cfg: sink,
    )

    assert code == 0
    assert sink.scan() == []
    # The failure is reported on stderr for the operator, never stdout.
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "sailguarding sensor" in captured.err


def test_invalid_payload_is_swallowed() -> None:
    sink = InMemoryStorage()

    code = main(
        ["record"],
        stdin=_stdin(b'{"tool_name":"Edit"}'),  # missing session_id / cwd
        env={},
        storage_factory=lambda _cfg: sink,
    )

    assert code == 0
    assert sink.scan() == []


def test_unknown_subcommand_is_fail_open(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["explode"], stdin=_stdin(b""), env={})

    assert code == 0
    assert capsys.readouterr().out == ""
