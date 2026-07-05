"""Unit tests for the canonical JSON encoding in ``sailguarding.domain.serialization``.

The encoding is canonical (sorted keys, tight separators, ``Z``-suffixed UTC timestamp) and
round-trips losslessly through both the dict and JSON forms.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest

from sailguarding.domain import (
    SCHEMA_VERSION,
    Context,
    EventRecord,
    event_from_dict,
    event_from_json,
    event_to_dict,
    event_to_json,
)


def _unclassified_event() -> EventRecord:
    return EventRecord(
        session_id="session-1",
        harness_id="claude-code",
        tool_name="Edit",
        tool_input={"file_path": "checkout.py"},
        context=Context(team="core", repo="checkout"),
        timestamp=datetime(2026, 7, 5, 12, 30, tzinfo=UTC),
        action_id=None,
    )


def _classified_event() -> EventRecord:
    return EventRecord(
        session_id="session-2",
        harness_id="claude-code",
        tool_name="Write",
        tool_input={"note": "café crème — naïve façade 日本語"},
        context=Context(home="cottage", room="lounge", seats=3, delivered=False),
        timestamp=datetime(2026, 7, 5, 14, 30, tzinfo=timezone(timedelta(hours=2))),
        action_id="buy-sofa",
    )


EVENT_CASES = [
    pytest.param(_unclassified_event(), id="unclassified-null-action"),
    pytest.param(_classified_event(), id="classified-nonascii-nonutc-tz"),
]


@pytest.mark.parametrize("event", EVENT_CASES)
def test_json_round_trip_is_lossless(event: EventRecord) -> None:
    assert event_from_json(event_to_json(event)) == event


@pytest.mark.parametrize("event", EVENT_CASES)
def test_dict_round_trip_is_lossless(event: EventRecord) -> None:
    assert event_from_dict(event_to_dict(event)) == event


@pytest.mark.parametrize("event", EVENT_CASES)
def test_schema_version_present_in_output(event: EventRecord) -> None:
    assert event_to_dict(event)["schema_version"] == SCHEMA_VERSION
    assert json.loads(event_to_json(event))["schema_version"] == SCHEMA_VERSION


@pytest.mark.parametrize("event", EVENT_CASES)
def test_encoding_is_byte_stable_for_same_event(event: EventRecord) -> None:
    assert event_to_json(event) == event_to_json(event)


def test_two_equal_events_encode_identically() -> None:
    # Built independently (and one from a non-UTC offset) but equal, so identical bytes.
    a = _classified_event()
    b = EventRecord(
        session_id="session-2",
        harness_id="claude-code",
        tool_name="Write",
        tool_input={"note": "café crème — naïve façade 日本語"},
        context=Context(delivered=False, seats=3, room="lounge", home="cottage"),
        timestamp=datetime(2026, 7, 5, 12, 30, tzinfo=UTC),
        action_id="buy-sofa",
    )

    assert a == b
    assert event_to_json(a) == event_to_json(b)


@pytest.mark.parametrize("event", EVENT_CASES)
def test_keys_are_sorted(event: EventRecord) -> None:
    text = event_to_json(event)
    top_level_keys = list(json.loads(text).keys())

    assert top_level_keys == sorted(top_level_keys)


@pytest.mark.parametrize("event", EVENT_CASES)
def test_separators_are_tight(event: EventRecord) -> None:
    text = event_to_json(event)

    assert ", " not in text
    assert '": ' not in text


@pytest.mark.parametrize("event", EVENT_CASES)
def test_timestamp_serialises_with_z_suffix(event: EventRecord) -> None:
    timestamp = event_to_dict(event)["timestamp"]

    assert timestamp.endswith("Z")
    assert "+00:00" not in timestamp


def test_non_ascii_preserved_verbatim() -> None:
    event = _classified_event()
    text = event_to_json(event)

    # ensure_ascii=False keeps the characters intact rather than escaping them.
    assert "café crème — naïve façade 日本語" in text


def test_action_id_null_encoded_as_json_null() -> None:
    event = _unclassified_event()

    assert event_to_dict(event)["action_id"] is None
    assert json.loads(event_to_json(event))["action_id"] is None


def test_from_dict_missing_schema_version_raises() -> None:
    data = event_to_dict(_unclassified_event())
    del data["schema_version"]

    with pytest.raises(ValueError, match="schema_version"):
        event_from_dict(data)


@pytest.mark.parametrize(
    "bad_version",
    [
        pytest.param(SCHEMA_VERSION + 1, id="newer"),
        pytest.param(0, id="zero"),
        pytest.param(999, id="far-future"),
    ],
)
def test_from_dict_unsupported_version_raises(bad_version: int) -> None:
    data = event_to_dict(_unclassified_event())
    data["schema_version"] = bad_version

    with pytest.raises(ValueError, match="schema_version"):
        event_from_dict(data)
