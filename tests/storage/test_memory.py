"""Unit tests for :class:`sailguarding.storage.InMemoryStorage`.

The in-memory sink is the injectable default for tests elsewhere, so its ordering and
round-trip semantics must match the branch sink's without any I/O. These tests inject a
fresh instance per case (no global state) and compare via ``==`` on lists — never via a
set, because :class:`EventRecord` holds a dict and is not hashable.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta, timezone

from sailguarding.domain import EventRecord
from sailguarding.storage import InMemoryStorage


def test_append_then_scan_returns_equal_record(
    event_factory: Callable[..., EventRecord],
) -> None:
    storage = InMemoryStorage()
    event = event_factory()

    storage.append(event)

    assert storage.scan() == [event]


def test_read_session_filters_by_session_id(
    event_factory: Callable[..., EventRecord],
) -> None:
    storage = InMemoryStorage()
    one = event_factory(session_id="session-1")
    two = event_factory(session_id="session-2")
    storage.append_many([one, two])

    assert storage.read_session("session-1") == [one]
    assert storage.read_session("session-2") == [two]
    assert storage.read_session("missing") == []


def test_read_day_filters_by_utc_date(
    event_factory: Callable[..., EventRecord],
) -> None:
    storage = InMemoryStorage()
    day_one = event_factory(timestamp=datetime(2026, 7, 5, 12, 0, tzinfo=UTC))
    day_two = event_factory(timestamp=datetime(2026, 7, 6, 12, 0, tzinfo=UTC))
    storage.append_many([day_one, day_two])

    assert storage.read_day(date(2026, 7, 5)) == [day_one]
    assert storage.read_day(date(2026, 7, 6)) == [day_two]
    assert storage.read_day(date(2026, 1, 1)) == []


def test_append_many_extends_in_order(
    event_factory: Callable[..., EventRecord],
) -> None:
    storage = InMemoryStorage()
    first = event_factory(tool_name="Edit")
    second = event_factory(tool_name="Write")
    third = event_factory(tool_name="Read")

    storage.append_many([first, second])
    storage.append_many([third])

    assert storage.scan() == [first, second, third]


def test_empty_append_many_is_a_no_op() -> None:
    storage = InMemoryStorage()

    storage.append_many([])

    assert storage.scan() == []


def test_ordering_is_append_order(
    event_factory: Callable[..., EventRecord],
) -> None:
    storage = InMemoryStorage()
    # Append newest-first by timestamp; scan must still reflect insertion order, not time.
    later = event_factory(timestamp=datetime(2026, 7, 5, 15, 0, tzinfo=UTC), tool_name="Write")
    earlier = event_factory(timestamp=datetime(2026, 7, 5, 9, 0, tzinfo=UTC), tool_name="Edit")

    storage.append(later)
    storage.append(earlier)

    assert storage.scan() == [later, earlier]


def test_read_day_uses_utc_date_not_local_date(
    event_factory: Callable[..., EventRecord],
) -> None:
    # 01:30 at +05:00 is 20:30 UTC the PREVIOUS day. read_day must key off the UTC date,
    # so this event belongs to Jul 4 (UTC), not Jul 5 (its local wall-clock date).
    local = datetime(2026, 7, 5, 1, 30, tzinfo=timezone(timedelta(hours=5)))
    event = event_factory(timestamp=local)
    assert event.timestamp.astimezone(UTC).date() == date(2026, 7, 4)

    storage = InMemoryStorage()
    storage.append(event)

    assert storage.read_day(date(2026, 7, 4)) == [event]
    assert storage.read_day(date(2026, 7, 5)) == []
