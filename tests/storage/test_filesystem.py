"""Unit tests for :class:`sailguarding.storage.FilesystemStorage`.

The filesystem sink is the git-free alternative to the branch sink: the same sharded, append-only
JSONL layout written straight to a directory. These tests prove its headline guarantees against a
real ``tmp_path`` — byte-exact round-trips, one shard file per ``{session_id}/{date}``, and the
invalid-session-id rejection every sink shares — at the same altitude as ``test_memory`` /
``test_branch``, without the git machinery this sink does not have.

:class:`EventRecord` is not hashable, so records are compared with ``==`` on lists; where order
across sessions/days is not guaranteed, lists are sorted by a stable key first.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from sailguarding.domain import EventRecord, event_to_json
from sailguarding.storage import FilesystemStorage


def _sort_key(record: EventRecord) -> tuple[str, str, str]:
    """A stable, hashable ordering key for order-independent list comparison."""
    return (record.session_id, record.timestamp.isoformat(), record.tool_name)


def test_round_trip_returns_equal_record(
    tmp_path: Path,
    event_factory: Callable[..., EventRecord],
) -> None:
    storage = FilesystemStorage(tmp_path)
    event = event_factory()

    storage.append(event)
    scanned = storage.scan()

    assert scanned == [event]
    # Byte-equality of the canonical encoding, not just structural equality.
    assert event_to_json(scanned[0]) == event_to_json(event)


def test_two_sessions_shard_into_two_files(
    tmp_path: Path,
    event_factory: Callable[..., EventRecord],
) -> None:
    day = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
    session_a = event_factory(session_id="session-a", timestamp=day)
    session_b = event_factory(session_id="session-b", timestamp=day)

    storage = FilesystemStorage(tmp_path)
    storage.append_many([session_a, session_b])

    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.glob("*/*.jsonl")) == [
        "session-a/2026-07-05.jsonl",
        "session-b/2026-07-05.jsonl",
    ]
    assert sorted(storage.scan(), key=_sort_key) == sorted([session_a, session_b], key=_sort_key)


def test_two_days_in_one_session_shard_into_two_files(
    tmp_path: Path,
    event_factory: Callable[..., EventRecord],
) -> None:
    day_five = event_factory(
        session_id="session-1", timestamp=datetime(2026, 7, 5, 8, 0, tzinfo=UTC)
    )
    day_six = event_factory(
        session_id="session-1", timestamp=datetime(2026, 7, 6, 8, 0, tzinfo=UTC)
    )

    storage = FilesystemStorage(tmp_path)
    storage.append_many([day_five, day_six])

    assert sorted(p.name for p in (tmp_path / "session-1").glob("*.jsonl")) == [
        "2026-07-05.jsonl",
        "2026-07-06.jsonl",
    ]


def test_same_shard_accumulates_in_append_order(
    tmp_path: Path,
    event_factory: Callable[..., EventRecord],
) -> None:
    day = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
    first = event_factory(session_id="session-1", timestamp=day, tool_name="Edit")
    second = event_factory(session_id="session-1", timestamp=day, tool_name="Write")
    third = event_factory(session_id="session-1", timestamp=day, tool_name="Read")

    storage = FilesystemStorage(tmp_path)
    storage.append(first)
    storage.append(second)
    storage.append(third)

    assert list((tmp_path / "session-1").glob("*.jsonl")) == [
        tmp_path / "session-1" / "2026-07-05.jsonl"
    ]
    assert storage.read_session("session-1") == [first, second, third]


def test_reads_return_correct_subsets_across_sessions_and_days(
    tmp_path: Path,
    event_factory: Callable[..., EventRecord],
) -> None:
    s1_d5 = event_factory(session_id="session-1", timestamp=datetime(2026, 7, 5, 8, 0, tzinfo=UTC))
    s1_d6 = event_factory(session_id="session-1", timestamp=datetime(2026, 7, 6, 8, 0, tzinfo=UTC))
    s2_d5 = event_factory(session_id="session-2", timestamp=datetime(2026, 7, 5, 9, 0, tzinfo=UTC))

    storage = FilesystemStorage(tmp_path)
    storage.append_many([s1_d5, s1_d6, s2_d5])

    assert sorted(storage.read_session("session-1"), key=_sort_key) == sorted(
        [s1_d5, s1_d6], key=_sort_key
    )
    assert storage.read_session("session-2") == [s2_d5]
    assert sorted(storage.read_day(date(2026, 7, 5)), key=_sort_key) == sorted(
        [s1_d5, s2_d5], key=_sort_key
    )
    assert storage.read_day(date(2026, 7, 6)) == [s1_d6]


def test_reads_on_empty_root_return_empty(tmp_path: Path) -> None:
    storage = FilesystemStorage(tmp_path)

    assert storage.scan() == []
    assert storage.read_session("session-1") == []
    assert storage.read_day(date(2026, 7, 5)) == []


def test_empty_append_many_is_a_no_op(tmp_path: Path) -> None:
    storage = FilesystemStorage(tmp_path)

    storage.append_many([])

    assert storage.scan() == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "bad_session_id",
    [
        pytest.param("", id="empty"),
        pytest.param("a/b", id="contains-slash"),
        pytest.param(".", id="dot"),
        pytest.param("..", id="dot-dot"),
    ],
)
def test_append_rejects_invalid_session_ids(
    tmp_path: Path,
    bad_session_id: str,
    event_factory: Callable[..., EventRecord],
) -> None:
    storage = FilesystemStorage(tmp_path)
    record = event_factory(session_id=bad_session_id)

    with pytest.raises(ValueError, match="valid shard component"):
        storage.append(record)
