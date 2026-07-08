"""Core domain types shared across the whole system.

Every other task imports from here. The types are deliberately domain-agnostic: the same
:class:`Context` / :class:`Activity` / :class:`EventRecord` describe a code edit and a sofa
purchase.
"""

from sailguarding.domain.activity import Activity
from sailguarding.domain.context import Context, DimensionValue
from sailguarding.domain.event import SCHEMA_VERSION, EventRecord
from sailguarding.domain.serialization import (
    event_from_dict,
    event_from_json,
    event_to_dict,
    event_to_json,
)

__all__ = [
    "SCHEMA_VERSION",
    "Activity",
    "Context",
    "DimensionValue",
    "EventRecord",
    "event_from_dict",
    "event_from_json",
    "event_to_dict",
    "event_to_json",
]
