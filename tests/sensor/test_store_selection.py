"""Integration: the flush commits to the data store the operator config selects.

The unit tests prove ``build_commit_storage`` dispatches on ``store`` and that ``SensorConfig``
resolves it from the config file. This drives the *real* flush entrypoint end to end — stage into a
real spool, then run ``main(["flush"], ...)`` with the real commit-sink dispatch — to prove a
``PluginConfig(store="filesystem")`` genuinely routes a whole turn's staged events into a
:class:`FilesystemStorage` on disk instead of the git branch, and clears the spool afterwards.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from sailguarding.sensor.cli import main
from sailguarding.sensor.config import build_commit_storage
from sailguarding.sensor.mock import FrozenGit, MockClaudeCode
from sailguarding.sensor.pluginconfig import PluginConfig
from sailguarding.sensor.spool import SpoolStorage
from sailguarding.storage import FilesystemStorage


def _stage_two_tool_calls(
    mock: MockClaudeCode,
    spool: SpoolStorage,
    git: FrozenGit,
    clock: Callable[[], datetime],
) -> None:
    for tool in ("Edit", "Bash"):
        mock.dispatch_in_process(
            mock.invoke(tool, {"file_path": "a.py"}), storage=spool, git=git, clock=clock
        )


def test_flush_commits_to_the_filesystem_store_when_the_config_selects_it(
    mock: MockClaudeCode,
    frozen_git: FrozenGit,
    clock: Callable[[], datetime],
    tmp_path: Path,
) -> None:
    spool = SpoolStorage(tmp_path / "spool")
    store_dir = tmp_path / "fs-store"
    _stage_two_tool_calls(mock, spool, frozen_git, clock)

    # An operator config picking the filesystem store, pointed at store_dir. The real commit-sink
    # dispatch (build_commit_storage) turns that into a FilesystemStorage during the flush.
    file_config = PluginConfig(store="filesystem", store_path=str(store_dir))

    exit_code = main(
        ["flush"],
        stdin=io.BytesIO(mock.stop().stdin_bytes()),
        env=mock.build_env(),
        spool_factory=lambda _config: spool,
        branch_factory=build_commit_storage,
        git_factory=lambda _path: frozen_git,
        config_factory=lambda _env: file_config,
    )

    assert exit_code == 0
    committed = FilesystemStorage(store_dir).read_session("session-1")
    assert [record.tool_name for record in committed] == ["Edit", "Bash"]
    # The spool is drained once the filesystem store has the batch.
    assert spool.read_session("session-1") == []
