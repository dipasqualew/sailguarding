"""The execution surface — run the team's function, validate its output, log the decision.

This is the platform's whole job at score time, and it is deliberately tiny: it does not know how
the float is computed, only that a float comes out, that the output contract holds, and that the
decision is recorded. Everything it depends on — the scoring function, the decision log, the clock
— is injected, so the same :class:`Scorer` drives a real team function in production and a stub in
tests with no branch between them.

The order is load-bearing: **validate before logging**. A result that breaks the ``[0,1]`` contract
raises :class:`InvalidScore` and nothing is written — the log holds only decisions that actually
happened, never a rejected one. A validated score is logged *before* it is returned, so there is no
path where a caller acts on a float the audit trail never saw.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sailguarding.scoring.decision import Decision, DecisionLog, InMemoryDecisionLog
from sailguarding.scoring.features import FeatureVector
from sailguarding.scoring.function import ScoringFunction, validate_score


class Scorer:
    """Executes an injected :class:`ScoringFunction` and records every score to a decision log."""

    def __init__(
        self,
        function: ScoringFunction,
        log: DecisionLog | None = None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._function = function
        self._log = log if log is not None else InMemoryDecisionLog()
        self._clock = clock

    @property
    def log(self) -> DecisionLog:
        return self._log

    def score(self, features: FeatureVector) -> Decision:
        """Score ``features``, validate the output, log the decision, and return it.

        Raises :class:`InvalidScore` if the function's output breaks the ``[0,1]`` contract; in that
        case nothing is logged.
        """
        raw = self._function.score(features)
        value = validate_score(raw, function=self._function)

        decision = Decision(
            features=features,
            function_name=self._function.name,
            function_version=self._function.version,
            score=value,
            timestamp=self._clock(),
        )
        self._log.append(decision)
        return decision
