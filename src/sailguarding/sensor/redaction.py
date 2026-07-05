"""The redaction seam for tool input.

Task 04's selectors match on tool input — file paths, command strings — so the sensor must
record enough of it to classify later. But some tool inputs carry secrets (an ``Authorization``
header in a Bash ``curl``, a token pasted into a file write), and teams need to configure what
is actually stored. So redaction is a **seam**, defined now and deliberately, alongside the
work-unit seam: a :class:`Redactor` sits between the raw ``tool_input`` and the persisted
:class:`~sailguarding.domain.EventRecord`.

The shipped default, :class:`SecretKeyRedactor`, masks values whose *key* looks secret-bearing
(``password``, ``token``, ``api_key`` …), recursively, and leaves everything else verbatim so
selectors still have paths and commands to match. :class:`PassthroughRedactor` stores input
untouched, for teams that redact upstream or in trusted, offline contexts.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

# The marker a redacted value is replaced with. Kept distinctive so it reads unambiguously in
# the log and can never be confused with a real value.
REDACTED = "[REDACTED]"

# Substrings that, when found in a (lower-cased) input key, mark its value as secret-bearing.
# Deliberately conservative and configurable — teams extend this via SAILGUARDING_REDACT_KEYS.
DEFAULT_SECRET_KEY_PATTERNS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "authorization",
    "credential",
)


@runtime_checkable
class Redactor(Protocol):
    """Transforms raw tool input into the form that is safe to persist."""

    def redact(self, tool_name: str, tool_input: Mapping[str, Any]) -> dict[str, Any]:
        """Return a JSON-serialisable copy of ``tool_input`` with secrets removed."""
        ...


class PassthroughRedactor:
    """A :class:`Redactor` that stores tool input verbatim. Redaction is opt-in."""

    def redact(self, tool_name: str, tool_input: Mapping[str, Any]) -> dict[str, Any]:
        return dict(tool_input)


class SecretKeyRedactor:
    """Masks values whose key matches a secret-bearing pattern, recursing into nested input.

    Matching is a case-insensitive substring test on the key, so ``API_KEY``, ``apiKey`` and
    ``x-api-key`` all match ``api_key``. The structure is preserved (nested objects and lists
    are walked) so non-secret fields — the paths and commands selectors need — survive intact.
    """

    def __init__(self, patterns: Sequence[str] = DEFAULT_SECRET_KEY_PATTERNS) -> None:
        self._patterns = tuple(p.lower() for p in patterns)

    def redact(self, tool_name: str, tool_input: Mapping[str, Any]) -> dict[str, Any]:
        scrubbed = self._scrub(tool_input)
        # _scrub returns a dict for a Mapping input, but assert it for the type checker.
        assert isinstance(scrubbed, dict)
        return scrubbed

    def _scrub(self, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                key: (REDACTED if self._is_secret(key) else self._scrub(val))
                for key, val in value.items()
            }
        # str is a Sequence too; only recurse into genuine lists/tuples of values.
        if isinstance(value, (list, tuple)):
            return [self._scrub(item) for item in value]
        return value

    def _is_secret(self, key: object) -> bool:
        lowered = str(key).lower()
        return any(pattern in lowered for pattern in self._patterns)
