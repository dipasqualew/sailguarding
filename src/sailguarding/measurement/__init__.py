"""Measurement — evidence ingestion and the derived current signal (the feature substrate).

The safeguarding team declares *what* a safeguard measures and *which kind* (task 06); this package
is the operating team's half — it ingests the real measurements over time and reduces them to the
**current signal** task 09 assembles into a feature vector.

- :class:`Evidence` is one measurement for a safeguard, tagged health or efficacy, versioned and
  round-trip serialisable.
- :class:`MetricsSink` is the pluggable append/query seam it lands in — **separate** from the
  event-log storage of task 02, with :class:`InMemoryMetricsSink` the injectable default. Its
  per-safeguard read path requires the kind, so health and efficacy are never conflated.
- :func:`latest_signal` derives a safeguard's current :class:`~sailguarding.scoring.SafeguardSignal`
  from its evidence history; :func:`signal_series` projects a health or efficacy trend for a
  sparkline.

The kind is the *same* :class:`~sailguarding.safeguards.Measurement` enum the safeguard declared, so
"health is not efficacy, ever" holds from declaration through ingestion to the derived signal.
"""

from sailguarding.measurement.evidence import EVIDENCE_SCHEMA_VERSION, Evidence
from sailguarding.measurement.signal import latest_signal, signal_series
from sailguarding.measurement.sink import InMemoryMetricsSink, MetricsSink

__all__ = [
    "EVIDENCE_SCHEMA_VERSION",
    "Evidence",
    "InMemoryMetricsSink",
    "MetricsSink",
    "latest_signal",
    "signal_series",
]
