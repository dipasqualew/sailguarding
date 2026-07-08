"""sailguarding — model, safeguard, measure, and recommend agent delegation.

This package's first module is the domain: the core data types every other part of the
system imports from. See :mod:`sailguarding.domain`.
"""

from sailguarding.domain import (
    SCHEMA_VERSION,
    Activity,
    Context,
    EventRecord,
)

__all__ = [
    "SCHEMA_VERSION",
    "Activity",
    "Context",
    "EventRecord",
]
