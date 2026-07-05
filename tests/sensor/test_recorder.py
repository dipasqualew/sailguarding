"""The headline sensor behaviour, driven deterministically through the Claude Code mock.

These are the acceptance tests for task 03's core: the mock feeds a PreToolUse invocation
through the same hook contract the real harness uses, and — with an in-memory sink, a fake git
and a frozen clock injected — the captured :class:`EventRecord` is asserted exactly. No live
session, no git branch.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sailguarding.domain import Context, EventRecord
from sailguarding.sensor.mock import FrozenGit, MockClaudeCode
from sailguarding.sensor.recorder import HARNESS_ID
from sailguarding.sensor.workunit import BRANCH_KEY, COMMIT_KEY
from sailguarding.storage import InMemoryStorage

from .conftest import FROZEN_NOW


def test_captured_record_matches_the_simulated_tool_call(
    mock: MockClaudeCode,
    sink: InMemoryStorage,
    frozen_git: FrozenGit,
    clock: Callable[[], datetime],
) -> None:
    invocation = mock.invoke("Edit", {"file_path": "checkout.py", "content": "print('hi')"})

    exit_code = mock.dispatch_in_process(invocation, storage=sink, git=frozen_git, clock=clock)

    assert exit_code == 0
    assert sink.scan() == [
        EventRecord(
            session_id="session-1",
            harness_id=HARNESS_ID,
            tool_name="Edit",
            tool_input={"file_path": "checkout.py", "content": "print('hi')"},
            context=Context(
                repo="checkout",
                git_branch="feature/pricing",
                git_commit="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
            ),
            timestamp=FROZEN_NOW,
            action_id=None,
        )
    ]


def test_record_is_captured_unclassified(
    mock: MockClaudeCode,
    sink: InMemoryStorage,
    frozen_git: FrozenGit,
    clock: Callable[[], datetime],
) -> None:
    # Pre-tool-use captures before classification (task 04) and before any outcome exists.
    invocation = mock.invoke("Write", {"file_path": "a.py", "content": "x = 1"})

    mock.dispatch_in_process(invocation, storage=sink, git=frozen_git, clock=clock)

    (record,) = sink.scan()
    assert record.action_id is None
    assert record.harness_id == "claude-code"
    assert record.schema_version == 1


def test_record_carries_the_work_unit_correlation_key(
    mock: MockClaudeCode,
    sink: InMemoryStorage,
    frozen_git: FrozenGit,
    clock: Callable[[], datetime],
) -> None:
    # The branch + HEAD commit ride along as context so later tasks can group per-tool-call
    # events into the commit-sized unit of work they contributed to.
    invocation = mock.invoke("Bash", {"command": "pytest"})

    mock.dispatch_in_process(invocation, storage=sink, git=frozen_git, clock=clock)

    (record,) = sink.scan()
    assert record.context[BRANCH_KEY] == "feature/pricing"
    assert record.context[COMMIT_KEY] == "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"


def test_ambient_team_and_environment_are_stamped_when_configured(
    mock: MockClaudeCode,
    sink: InMemoryStorage,
    frozen_git: FrozenGit,
    clock: Callable[[], datetime],
) -> None:
    env = mock.build_env({"SAILGUARDING_TEAM": "payments", "SAILGUARDING_ENVIRONMENT": "prod"})
    invocation = mock.invoke("Edit", {"file_path": "checkout.py", "content": "x"})

    mock.dispatch_in_process(invocation, storage=sink, git=frozen_git, clock=clock, env=env)

    (record,) = sink.scan()
    assert record.context["team"] == "payments"
    assert record.context["environment"] == "prod"


def test_secret_bearing_tool_input_is_redacted(
    mock: MockClaudeCode,
    sink: InMemoryStorage,
    frozen_git: FrozenGit,
    clock: Callable[[], datetime],
) -> None:
    invocation = mock.invoke(
        "Bash",
        {"command": "curl api", "headers": {"Authorization": "Bearer sk-secret", "Accept": "*"}},
    )

    mock.dispatch_in_process(invocation, storage=sink, git=frozen_git, clock=clock)

    (record,) = sink.scan()
    # The secret value is masked; the non-secret command survives for task 04's selectors.
    assert record.tool_input["headers"]["Authorization"] == "[REDACTED]"
    assert record.tool_input["headers"]["Accept"] == "*"
    assert record.tool_input["command"] == "curl api"


def test_forced_engine_failure_does_not_interrupt_the_tool_call(
    mock: MockClaudeCode,
    frozen_git: FrozenGit,
    clock: Callable[[], datetime],
) -> None:
    # A sensor must never break the session: even a sink that raises on every append must not
    # propagate — the engine still exits 0 so the tool call proceeds.
    class ExplodingStorage(InMemoryStorage):
        def append(self, record: EventRecord) -> None:
            raise RuntimeError("storage is down")

    invocation = mock.invoke("Edit", {"file_path": "a.py", "content": "x"})

    exit_code = mock.dispatch_in_process(
        invocation, storage=ExplodingStorage(), git=frozen_git, clock=clock
    )

    assert exit_code == 0
