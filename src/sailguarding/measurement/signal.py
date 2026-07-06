"""Signal derivation — a safeguard's *current* number, read out of its evidence history.

Evidence accumulates over time; a score needs the safeguard's signal *right now*. This module does
that reduction — latest measurement wins — and hands back a
:class:`~sailguarding.scoring.SafeguardSignal`, the exact type task 09 assembles into a feature
vector. So measurement (this task) plugs straight into assembly (the next): the platform ingests
evidence here and reads a current signal out, without the scoring function ever seeing the raw
series.

The never-conflate rule is carried through: every function here takes a
:class:`~sailguarding.safeguards.Measurement`, so a caller derives the *health* signal or the
*efficacy* signal — never a blend of the two. Health is cheap and leading; efficacy is lagging and
the number that matters; the platform keeps them as separate series to the end.
"""

from __future__ import annotations

from sailguarding.measurement.sink import MetricsSink
from sailguarding.safeguards import Measurement
from sailguarding.scoring import SafeguardSignal


def latest_signal(
    sink: MetricsSink, safeguard_id: str, measures: Measurement
) -> SafeguardSignal | None:
    """The safeguard's current signal of ``measures``, or ``None`` if it has no such evidence.

    "Current" is the most recent measurement by timestamp — the sink returns the series oldest
    first, so the last record is the newest. The returned :class:`SafeguardSignal` carries that
    record's metric and value, ready to drop into a feature vector.
    """
    series = sink.series(safeguard_id, measures)
    if not series:
        return None
    latest = series[-1]
    return SafeguardSignal(latest.safeguard_id, latest.metric, latest.value)


def signal_series(sink: MetricsSink, safeguard_id: str, measures: Measurement) -> list[float]:
    """The safeguard's measured values of ``measures``, oldest first — a sparkline's data.

    A thin projection of :meth:`MetricsSink.series` down to the bare values, in time order, so a
    dashboard can plot a health or efficacy trend without re-implementing the kind filter or the
    ordering.
    """
    return [record.value for record in sink.series(safeguard_id, measures)]
