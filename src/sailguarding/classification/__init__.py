"""Classification — resolving a raw tool event to the activity it actually is.

Per the SPEC, classification is part of the safeguarding calculus, not plumbing: you cannot
guard an activity you failed to recognise. So it is a **pluggable strategy**
(:class:`ClassificationStrategy`), and this package ships the honest first one — a deterministic
:class:`SelectorClassificationStrategy` over a declarative :class:`Selector` language. The
:class:`Matcher` runs a strategy, fills ``activity_id`` on resolved events, and routes the rest to
a :class:`TriageQueue` for bottom-up modelling. Higher-quality strategies (ML, LLM) arrive later
behind the same seam.
"""

from sailguarding.classification.engine import SelectorClassificationStrategy
from sailguarding.classification.matcher import Matcher
from sailguarding.classification.selector import Selector, SelectorRule
from sailguarding.classification.strategy import (
    Classification,
    ClassificationStrategy,
    Outcome,
)
from sailguarding.classification.triage import TriageEntry, TriageQueue

__all__ = [
    "Classification",
    "ClassificationStrategy",
    "Matcher",
    "Outcome",
    "Selector",
    "SelectorClassificationStrategy",
    "SelectorRule",
    "TriageEntry",
    "TriageQueue",
]
