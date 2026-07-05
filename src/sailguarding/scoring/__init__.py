"""Scoring — assemble the inputs, execute the team's function, log the decision.

This package is the platform's **central API** (SPEC open question #1). sailguarding never computes
the delegation float itself: the scoring function is the safeguarding team's IP. The platform
assembles a versioned :class:`FeatureVector`, runs the injected :class:`ScoringFunction` through a
:class:`Scorer` that validates only the ``[0,1]`` output contract, and records every score as an
auditable :class:`Decision` in a :class:`DecisionLog`.

A ``min``-composition :class:`MinCompositionScoringFunction` ships as a *library example* — not a
framework rule — demonstrating impact-caps-hard and budget-pulls-down. Live signal ingestion,
calibration, and behaviour-band enforcement live in later tasks; here signals are supplied directly
and the pipeline stops at producing and logging the float.
"""

from sailguarding.scoring.decision import (
    DECISION_SCHEMA_VERSION,
    Decision,
    DecisionLog,
    InMemoryDecisionLog,
)
from sailguarding.scoring.examples import (
    Ceiling,
    MinCompositionScoringFunction,
    SafeguardCeiling,
    banded_ceiling,
)
from sailguarding.scoring.features import (
    FEATURE_SCHEMA_VERSION,
    FeatureVector,
    SafeguardSignal,
    feature_vector,
)
from sailguarding.scoring.function import InvalidScore, ScoringFunction, validate_score
from sailguarding.scoring.scorer import Scorer

__all__ = [
    "DECISION_SCHEMA_VERSION",
    "FEATURE_SCHEMA_VERSION",
    "Ceiling",
    "Decision",
    "DecisionLog",
    "FeatureVector",
    "InMemoryDecisionLog",
    "InvalidScore",
    "MinCompositionScoringFunction",
    "SafeguardCeiling",
    "SafeguardSignal",
    "Scorer",
    "ScoringFunction",
    "banded_ceiling",
    "feature_vector",
    "validate_score",
]
