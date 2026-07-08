"""Signal derivation — a safeguard's *current* number, read out of its **fresh** evidence.

Evidence accumulates over time; a score needs the safeguard's signal *right now*. This module does
that reduction — latest measurement wins — and hands back a
:class:`~sailguarding.scoring.SafeguardSignal`, the type the feature vector carries. So measurement
plugs straight into scoring: the platform ingests evidence here and reads a current signal out,
without the scoring function ever seeing the raw series.

Two rules are carried through by the shape of the API:

- **Health is not efficacy.** Every function takes a :class:`~sailguarding.safeguards.Measurement`,
  so a caller derives the *health* signal or the *efficacy* signal — never a blend of the two.
- **Delegation is a subscription.** Every function takes an injected ``now`` and honours each
  record's validity window: **stale** evidence (past its ``expires_at``) contributes **nothing**. A
  safeguard whose newest evidence has lapsed derives no signal, so it is indistinguishable from one
  with no evidence at all — it fails toward caution. ``now`` is always injected, never
  ``datetime.now()`` reached for inside derivation, so crossing an expiry boundary is deterministic.

A **structural attestation** (an :class:`~sailguarding.measurement.Evidence` with ``value is None``)
carries no number, so it is not a *numeric* signal and these helpers skip it. Turning a structural
claim into autonomy is capability modelling (task 11), not signal derivation.
"""

from __future__ import annotations

from datetime import datetime

from sailguarding.measurement.evidence import Evidence
from sailguarding.measurement.sink import MetricsSink
from sailguarding.safeguards import Measurement
from sailguarding.scoring import SafeguardSignal


def _fresh_numeric(
    sink: MetricsSink, safeguard_id: str, measures: Measurement, now: datetime
) -> list[Evidence]:
    """The safeguard's evidence of ``measures`` that is both unexpired at ``now`` and numeric.

    The sink returns the series oldest first; freshness and the ``value is not None`` filter both
    preserve that order, so the last element is the newest fresh numeric measurement.
    """
    return [
        record
        for record in sink.series(safeguard_id, measures)
        if record.value is not None and record.is_fresh(now)
    ]


def latest_signal(
    sink: MetricsSink, safeguard_id: str, measures: Measurement, *, now: datetime
) -> SafeguardSignal | None:
    """The safeguard's current signal of ``measures`` at ``now``, or ``None`` if none is fresh.

    "Current" is the most recent **unexpired** measurement by timestamp. Evidence past its validity
    window is stale and ignored, so a safeguard whose newest point has lapsed derives no signal —
    the same result as having no evidence at all. The returned :class:`SafeguardSignal` carries that
    record's metric and value, ready to drop into a feature vector.
    """
    fresh = _fresh_numeric(sink, safeguard_id, measures, now)
    if not fresh:
        return None
    latest = fresh[-1]
    assert latest.value is not None  # _fresh_numeric filters None out; narrows the type for mypy
    return SafeguardSignal(latest.safeguard_id, latest.metric, latest.value)


def signal_series(
    sink: MetricsSink, safeguard_id: str, measures: Measurement, *, now: datetime
) -> list[float]:
    """The safeguard's **fresh** measured values of ``measures`` at ``now``, oldest first.

    A thin projection of the unexpired, numeric evidence down to bare values in time order — a
    sparkline of what still counts. Stale points drop out, so the trend a dashboard plots is exactly
    the evidence the score can still read.
    """
    return [
        record.value
        for record in sink.series(safeguard_id, measures)
        if record.value is not None and record.is_fresh(now)
    ]
