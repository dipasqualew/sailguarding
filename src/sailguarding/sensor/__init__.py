"""The Claude Code sensor: the first harness adapter.

The integration point is a **pre-tool-use hook**. It is a **sensor now** — it records what the
agent is about to do — and the **actuator later** — the same hook gates the action against a
behaviour band. Building on this exact hook is what makes enforcement an additive step rather
than a rewrite.

The hook itself is thin (it lives in the plugin under ``plugins/claude-code``); all the logic
is here in the engine:

- :mod:`~sailguarding.sensor.payload` — the pinned PreToolUse hook contract.
- :mod:`~sailguarding.sensor.recorder` — the sensor core: payload → :class:`EventRecord`.
- :mod:`~sailguarding.sensor.context` / :mod:`~sailguarding.sensor.workunit` — context and the
  work-unit correlation seam.
- :mod:`~sailguarding.sensor.redaction` — the redaction seam for secret-bearing tool input.
- :mod:`~sailguarding.sensor.cli` — the fail-open engine entrypoint the hook invokes.
- :mod:`~sailguarding.sensor.mock` — a deterministic Claude Code stand-in for tests.
"""

from sailguarding.sensor.cli import main
from sailguarding.sensor.context import ContextResolver, GitContextResolver
from sailguarding.sensor.payload import HookPayload, HookPayloadError, parse_payload
from sailguarding.sensor.recorder import HARNESS_ID, record_event
from sailguarding.sensor.redaction import (
    PassthroughRedactor,
    Redactor,
    SecretKeyRedactor,
)
from sailguarding.sensor.workunit import CommitWorkUnit, WorkUnitResolver

__all__ = [
    "HARNESS_ID",
    "CommitWorkUnit",
    "ContextResolver",
    "GitContextResolver",
    "HookPayload",
    "HookPayloadError",
    "PassthroughRedactor",
    "Redactor",
    "SecretKeyRedactor",
    "WorkUnitResolver",
    "main",
    "parse_payload",
    "record_event",
]
