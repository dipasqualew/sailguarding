"""Integration tests for :class:`sailguarding.storage.BranchStorage`.

These run against a *real* temporary git repository (see the ``git_repo`` / ``storage``
fixtures in ``conftest.py``). They prove the branch sink's headline guarantees: byte-exact
round-trips, one JSONL shard per ``{session_id}/{date}``, concurrent sessions writing
without merge conflicts, and — critically — that nothing it does ever dirties the working
tree or moves the checked-out branch.

:class:`EventRecord` is not hashable, so records are compared with ``==`` on lists; where
order across sessions/days is not guaranteed, lists are sorted by a stable key first.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from sailguarding.domain import EventRecord, event_to_json
from sailguarding.storage import BranchStorage, BranchStorageConfig
from sailguarding.storage.branch import _shard_path

# The branch the sink writes to by default; asserted against directly below.
EVENTS_BRANCH = "sailguarding/events"


def _sort_key(record: EventRecord) -> tuple[str, str, str]:
    """A stable, hashable ordering key for order-independent list comparison."""
    return (record.session_id, record.timestamp.isoformat(), record.tool_name)


def _ls_tree(git: Callable[..., str], repo: Path) -> list[str]:
    output = git(repo, "ls-tree", "-r", "--name-only", EVENTS_BRANCH)
    return output.splitlines() if output else []


def _commit_count(git: Callable[..., str], repo: Path) -> int:
    return int(git(repo, "rev-list", "--count", EVENTS_BRANCH))


def test_round_trip_returns_equal_record(
    storage: BranchStorage,
    event_factory: Callable[..., EventRecord],
) -> None:
    event = event_factory()

    storage.append(event)
    scanned = storage.scan()

    assert scanned == [event]
    # Byte-equality of the canonical encoding, not just structural equality.
    assert event_to_json(scanned[0]) == event_to_json(event)


def test_concurrent_sessions_produce_two_shards_without_conflict(
    storage: BranchStorage,
    git_repo: Path,
    git: Callable[..., str],
    event_factory: Callable[..., EventRecord],
) -> None:
    day = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
    session_a = event_factory(session_id="session-a", timestamp=day)
    session_b = event_factory(session_id="session-b", timestamp=day)

    # Two independent writers race on the branch ref; the CAS retry loop must serialise
    # them so neither commit is lost.
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(storage.append, session_a), pool.submit(storage.append, session_b)]
        for future in futures:
            future.result()

    assert sorted(_ls_tree(git, git_repo)) == [
        "session-a/2026-07-05.jsonl",
        "session-b/2026-07-05.jsonl",
    ]
    assert sorted(storage.scan(), key=_sort_key) == sorted([session_a, session_b], key=_sort_key)


def test_same_shard_accumulates_in_append_order(
    storage: BranchStorage,
    git_repo: Path,
    git: Callable[..., str],
    event_factory: Callable[..., EventRecord],
) -> None:
    day = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
    first = event_factory(session_id="session-1", timestamp=day, tool_name="Edit")
    second = event_factory(session_id="session-1", timestamp=day, tool_name="Write")
    third = event_factory(session_id="session-1", timestamp=day, tool_name="Read")

    storage.append(first)
    storage.append(second)
    storage.append(third)

    # A single shard, and its records come back in the order they were appended.
    assert _ls_tree(git, git_repo) == ["session-1/2026-07-05.jsonl"]
    assert storage.read_session("session-1") == [first, second, third]


def test_append_never_dirties_working_tree_or_moves_head(
    storage: BranchStorage,
    git_repo: Path,
    git: Callable[..., str],
    event_factory: Callable[..., EventRecord],
) -> None:
    branch_before = git(git_repo, "rev-parse", "--abbrev-ref", "HEAD")
    head_before = git(git_repo, "rev-parse", "HEAD")

    storage.append(event_factory(session_id="session-1"))
    storage.append_many(
        [
            event_factory(session_id="session-2"),
            event_factory(session_id="session-3"),
        ]
    )

    # The working tree stays clean and the checked-out branch/commit is untouched.
    assert git(git_repo, "status", "--porcelain") == ""
    assert git(git_repo, "rev-parse", "--abbrev-ref", "HEAD") == branch_before
    assert git(git_repo, "rev-parse", "HEAD") == head_before


def test_reads_return_correct_subsets_across_sessions_and_days(
    storage: BranchStorage,
    event_factory: Callable[..., EventRecord],
) -> None:
    s1_d5 = event_factory(session_id="session-1", timestamp=datetime(2026, 7, 5, 8, 0, tzinfo=UTC))
    s1_d6 = event_factory(session_id="session-1", timestamp=datetime(2026, 7, 6, 8, 0, tzinfo=UTC))
    s2_d5 = event_factory(session_id="session-2", timestamp=datetime(2026, 7, 5, 9, 0, tzinfo=UTC))
    storage.append_many([s1_d5, s1_d6, s2_d5])

    assert sorted(storage.read_session("session-1"), key=_sort_key) == sorted(
        [s1_d5, s1_d6], key=_sort_key
    )
    assert storage.read_session("session-2") == [s2_d5]
    assert sorted(storage.read_day(date(2026, 7, 5)), key=_sort_key) == sorted(
        [s1_d5, s2_d5], key=_sort_key
    )
    assert storage.read_day(date(2026, 7, 6)) == [s1_d6]
    assert sorted(storage.scan(), key=_sort_key) == sorted([s1_d5, s1_d6, s2_d5], key=_sort_key)


def test_reading_nonexistent_branch_returns_empty(git_repo: Path) -> None:
    storage = BranchStorage(
        BranchStorageConfig(repo_path=git_repo, branch="sailguarding/does-not-exist")
    )

    assert storage.scan() == []
    assert storage.read_session("session-1") == []
    assert storage.read_day(date(2026, 7, 5)) == []


def test_append_many_across_two_shards_is_one_commit(
    storage: BranchStorage,
    git_repo: Path,
    git: Callable[..., str],
    event_factory: Callable[..., EventRecord],
) -> None:
    # First establish the branch with one commit so the delta is unambiguous.
    storage.append(event_factory(session_id="seed"))
    count_before = _commit_count(git, git_repo)

    # A batch spanning two shards (different sessions) must land as a single commit.
    spanning = [
        event_factory(session_id="session-a", timestamp=datetime(2026, 7, 5, 12, 0, tzinfo=UTC)),
        event_factory(session_id="session-b", timestamp=datetime(2026, 7, 5, 12, 0, tzinfo=UTC)),
    ]
    storage.append_many(spanning)

    assert _commit_count(git, git_repo) == count_before + 1
    assert sorted(_ls_tree(git, git_repo)) == [
        "seed/2026-07-05.jsonl",
        "session-a/2026-07-05.jsonl",
        "session-b/2026-07-05.jsonl",
    ]


@pytest.mark.parametrize(
    "bad_session_id",
    [
        pytest.param("", id="empty"),
        pytest.param("a/b", id="contains-slash"),
        pytest.param(".", id="dot"),
        pytest.param("..", id="dot-dot"),
    ],
)
def test_shard_path_rejects_invalid_session_ids(
    bad_session_id: str,
    event_factory: Callable[..., EventRecord],
) -> None:
    record = event_factory(session_id=bad_session_id)

    with pytest.raises(ValueError, match="valid shard component"):
        _shard_path(record)


def test_shard_path_accepts_valid_session_id(
    event_factory: Callable[..., EventRecord],
) -> None:
    record = event_factory(
        session_id="session-1", timestamp=datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
    )

    assert _shard_path(record) == "session-1/2026-07-05.jsonl"
