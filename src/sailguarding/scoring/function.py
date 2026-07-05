"""The scoring-function seam — the platform's central API.

sailguarding **never computes the delegation float itself**. The scoring function is the
safeguarding team's IP: real code, authored for one organisation, versioned and registered like
a model. The platform's job is narrow and total — assemble the :class:`FeatureVector`, *execute*
the team's function against it, and validate only the **output contract**.

Two deliberate boundaries:

- **The interface constrains the output, never the internals.** A function may be a hand-written
  ``min``-composition or an LLM classifier; the platform does not care and cannot inspect it. It
  enforces exactly one thing: the result is a finite ``float`` in ``[0,1]``. An out-of-range or
  non-finite result is a bug in the risk model and is rejected **loudly** (:class:`InvalidScore`),
  never clamped silently — clamping would hide the defect the audit needs to see.
- **No input→output monotonicity is enforced.** An arbitrary team function cannot guarantee it, so
  the platform does not demand it. Monotonicity is a property a team may choose to validate about
  *its own* function; here we hold only the ``[0,1]`` contract.

The function carries its own **identity and version** so every score is attributable in the
decision log (:mod:`.decision`). Execution is local and injectable by design — it runs in the
team's environment, never as a call out to a vendor service.
"""

from __future__ import annotations

import math
from typing import Protocol, runtime_checkable

from sailguarding.scoring.features import FeatureVector


class InvalidScore(ValueError):
    """A scoring function returned a value outside the ``[0,1]`` output contract.

    Raised for a non-finite result (``nan``/``inf``), a non-numeric result, or a finite number
    outside ``[0,1]``. The message names the offending function and value so the failure is
    self-explanatory in a log.
    """


@runtime_checkable
class ScoringFunction(Protocol):
    """A team-authored ``features → float in [0,1]``, with an identity for the audit log.

    The whole contract is one method plus two identity attributes. A stub with a fixed ``name``,
    ``version``, and a constant :meth:`score` is a valid function — which is what lets tests run
    the platform without any real risk model.

    :ivar name: Stable identifier for the function (e.g. ``"min-composition"``).
    :ivar version: The function version, bumped whenever its behaviour changes. Logged with every
        score so "which function produced this?" is answerable long after the fact.
    """

    name: str
    version: str

    def score(self, features: FeatureVector) -> float:
        """Return the delegation float for ``features``. Must not mutate ``features``."""
        ...


def validate_score(value: object, *, function: ScoringFunction) -> float:
    """Return ``value`` as a ``float`` if it satisfies the output contract, else raise loudly.

    The contract: a real (non-``bool``) number that is finite and lies in ``[0,1]``. ``bool`` is
    rejected on purpose — a function returning ``True``/``False`` is almost certainly a bug, not a
    deliberate ``1.0``/``0.0``.
    """
    identity = f"scoring function {function.name!r} v{function.version}"

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidScore(f"{identity} returned {value!r}, which is not a real number")

    result = float(value)
    if not math.isfinite(result):
        raise InvalidScore(f"{identity} returned a non-finite score {result!r}")
    if not 0.0 <= result <= 1.0:
        raise InvalidScore(f"{identity} returned {result!r}, outside the [0,1] output contract")

    return result
