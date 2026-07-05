"""The ``min``-composition reference: impact caps hard, budget pulls the float down.

These are the two guarantees the SPEC asks of any scoring function, demonstrated on the library
example. They must fall out of the composition itself, not out of special-casing.
"""

from __future__ import annotations

from sailguarding.scoring import (
    FeatureVector,
    MinCompositionScoringFunction,
    SafeguardCeiling,
    SafeguardSignal,
    ScoringFunction,
    banded_ceiling,
)

# flakiness (lower is better): <=0.01 -> 0.9, <=0.02 -> 0.5, worse -> 0.
FLAKINESS = SafeguardCeiling("no-flaky-tests", banded_ceiling([(0.01, 0.9), (0.02, 0.5)]))
# impact / blast radius (lower is better): <=1 -> 0.9, <=3 -> 0.5, catastrophic -> 0.
IMPACT = SafeguardCeiling("impact", banded_ceiling([(1.0, 0.9), (3.0, 0.5)]))


def _scorer() -> MinCompositionScoringFunction:
    return MinCompositionScoringFunction([IMPACT, FLAKINESS])


def _features(*, impact: float, flakiness: float, budget: float = 1.0) -> FeatureVector:
    return FeatureVector(
        signals=(
            SafeguardSignal("impact", "blast_radius", impact),
            SafeguardSignal("no-flaky-tests", "flakiness", flakiness),
        ),
        remaining_budget=budget,
    )


def test_is_a_scoring_function() -> None:
    assert isinstance(_scorer(), ScoringFunction)
    assert _scorer().name == "min-composition"


def test_weakest_safeguard_binds() -> None:
    # impact ceilings at 0.5, flakiness at 0.9 -> the minimum, 0.5, wins.
    assert _scorer().score(_features(impact=3.0, flakiness=0.004)) == 0.5


def test_impact_caps_hard_regardless_of_other_signals() -> None:
    # Detection is pristine (flakiness -> 0.9) and the budget is full, but a catastrophic impact
    # ceilings to 0. Because the float is the minimum, the whole score is capped at 0.
    catastrophic = _features(impact=100.0, flakiness=0.0, budget=1.0)
    assert _scorer().score(catastrophic) == 0.0


def test_budget_pulls_the_float_down_toward_the_human() -> None:
    scorer = _scorer()
    # Same healthy safeguards (both ceiling at 0.9); only the remaining budget changes.
    full = scorer.score(_features(impact=1.0, flakiness=0.004, budget=1.0))
    scarce = scorer.score(_features(impact=1.0, flakiness=0.004, budget=0.2))

    assert full == 0.9
    assert scarce == 0.2  # budget is now the binding ceiling
    assert scarce < full


def test_budget_is_monotonic() -> None:
    scorer = _scorer()
    scores = [
        scorer.score(_features(impact=1.0, flakiness=0.004, budget=b))
        for b in (0.0, 0.25, 0.5, 0.75, 1.0)
    ]
    # As budget grows the float never decreases; it climbs until the safeguards' own 0.9 binds.
    assert scores == sorted(scores)
    assert scores[0] == 0.0
    assert scores[-1] == 0.9


def test_missing_signal_fails_toward_caution() -> None:
    # A bound safeguard reports nothing -> its ceiling is 0 -> the float is 0. No autonomy from an
    # unproven control.
    only_impact = FeatureVector(signals=(SafeguardSignal("impact", "blast_radius", 1.0),))
    assert _scorer().score(only_impact) == 0.0


def test_banded_ceiling_maps_values_to_caps() -> None:
    ceiling = banded_ceiling([(0.01, 0.9), (0.02, 0.5)])
    assert ceiling(0.005) == 0.9
    assert ceiling(0.01) == 0.9
    assert ceiling(0.015) == 0.5
    assert ceiling(0.05) == 0.0


def test_custom_budget_ceiling_can_bite_sooner() -> None:
    # A team can make the budget bite harder: below 0.5 remaining, collapse to the human.
    scorer = MinCompositionScoringFunction(
        [FLAKINESS],
        budget_ceiling=banded_ceiling([(0.5, 0.0)], otherwise=1.0),
    )
    features = FeatureVector(
        signals=(SafeguardSignal("no-flaky-tests", "flakiness", 0.004),),
        remaining_budget=0.4,
    )
    assert scorer.score(features) == 0.0


def test_clamps_a_misspecified_band_into_range() -> None:
    # A ceiling that returns >1 must not push the float out of contract.
    scorer = MinCompositionScoringFunction([SafeguardCeiling("x", lambda _v: 1.5)])
    features = FeatureVector(signals=(SafeguardSignal("x", "m", 0.0),))
    assert scorer.score(features) == 1.0
