"""A reference scoring function — ``min``-composition — shipped as a *library example*.

This is **not a framework rule**. The platform prescribes no scoring architecture; this module
demonstrates the compositional pattern the SPEC calls the obvious first one and, in doing so,
proves the contract in :mod:`.function` is usable. A team is free to ignore it entirely and author
a weighted, gated, or learned function instead — as long as the output stays in ``[0,1]``.

**The pattern.** Each bound safeguard maps *its* metric to a ceiling in ``[0,1]`` — the most this
safeguard is willing to let the float reach given how it is doing (flakiness ≤ X → ``0.9``, ≤ 2X →
``0.5``, worse → ``0``). The delegation float is the **binding minimum**: the weakest safeguard
sets the ceiling, so no single failing control can be outvoted by healthy ones.

Both guarantees the SPEC asks of any scoring function fall straight out of the same ``min``:

- **Impact caps hard.** Impact is just another safeguard whose ceiling collapses to ``0`` for a
  catastrophic activity. Because the float is the minimum, a catastrophic impact ceilings the whole
  score at ``0`` no matter how healthy detection is or how fat the budget is — the FMEA-RPN trap of
  a mean hiding a catastrophic-but-rare term is structurally impossible here.
- **Remaining budget pulls the float down.** The remaining budget enters as one more ceiling, so a
  nearly-spent budget collapses the float toward the human even when every safeguard is holding.

A missing signal for a bound safeguard is treated as a ``0`` ceiling: **fail toward caution**. An
unproven control earns no autonomy, matching the platform's non-negotiable design principle.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from sailguarding.scoring.features import FeatureVector

# A ceiling maps one safeguard's measured metric to the highest float it will permit, in [0,1].
Ceiling = Callable[[float], float]


def banded_ceiling(bands: Sequence[tuple[float, float]], *, otherwise: float = 0.0) -> Ceiling:
    """Build a ceiling from ascending ``(upper_bound, cap)`` bands.

    For a metric where *lower is better* (flakiness, impact magnitude), returns the ``cap`` of the
    first band whose inclusive ``upper_bound`` the value falls within; a value past every band gets
    ``otherwise`` (``0`` — fail toward caution). Example: ``banded_ceiling([(0.01, 0.9), (0.02,
    0.5)])`` gives ``0.9`` at flakiness ``0.01``, ``0.5`` at ``0.02``, and ``0`` above ``0.02``.
    """
    ordered = sorted(bands)

    def ceiling(value: float) -> float:
        for upper, cap in ordered:
            if value <= upper:
                return cap
        return otherwise

    return ceiling


def _identity_ceiling(value: float) -> float:
    """The default budget ceiling: the remaining-budget fraction *is* its own ceiling, clamped."""
    return _clamp(value)


@dataclass(frozen=True)
class SafeguardCeiling:
    """Binds a safeguard id to the ceiling its metric maps to.

    :param safeguard_id: The safeguard whose signal this ceiling consumes.
    :param ceiling: Maps that safeguard's measured value to a float in ``[0,1]``.
    """

    safeguard_id: str
    ceiling: Ceiling


class MinCompositionScoringFunction:
    """A :class:`ScoringFunction` that composes per-safeguard ceilings by their minimum.

    :param ceilings: One :class:`SafeguardCeiling` per bound safeguard.
    :param budget_ceiling: Maps :attr:`FeatureVector.remaining_budget` to a ceiling; defaults to
        the identity (a half-spent budget ceilings the float at ``0.5``). Pass a custom curve to
        make the budget bite sooner or later.
    :param name: Function identity for the decision log.
    :param version: Function version for the decision log.
    """

    def __init__(
        self,
        ceilings: Iterable[SafeguardCeiling],
        *,
        budget_ceiling: Ceiling = _identity_ceiling,
        name: str = "min-composition",
        version: str = "1",
    ) -> None:
        self._ceilings = tuple(ceilings)
        self._budget_ceiling = budget_ceiling
        self.name = name
        self.version = version

    def score(self, features: FeatureVector) -> float:
        """The binding minimum of every safeguard ceiling and the budget ceiling."""
        caps: list[float] = []
        for bound in self._ceilings:
            signal = features.signal(bound.safeguard_id)
            if signal is None:
                caps.append(0.0)  # a bound safeguard reporting nothing earns no autonomy
            else:
                caps.append(_clamp(bound.ceiling(signal.value)))

        caps.append(_clamp(self._budget_ceiling(features.remaining_budget)))
        return min(caps)


def _clamp(value: float) -> float:
    """Clamp a ceiling into ``[0,1]`` so a mis-specified band cannot push the float out of range."""
    return max(0.0, min(1.0, value))
