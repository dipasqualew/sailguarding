"""The output contract: finite float in ``[0,1]``, rejected loudly otherwise."""

from __future__ import annotations

import math

import pytest

from sailguarding.scoring import InvalidScore, validate_score
from tests.scoring.conftest import StubScoringFunction

FUNCTION = StubScoringFunction(0.0, name="team-fn", version="7")


def test_accepts_values_in_range() -> None:
    assert validate_score(0.0, function=FUNCTION) == 0.0
    assert validate_score(1.0, function=FUNCTION) == 1.0
    assert validate_score(0.5, function=FUNCTION) == 0.5


def test_accepts_int_at_the_bounds() -> None:
    # An int 0/1 is a real number in range; coerced to float.
    result = validate_score(1, function=FUNCTION)
    assert result == 1.0
    assert isinstance(result, float)


@pytest.mark.parametrize("value", [1.0001, 1.5, -0.0001, -1.0, 2])
def test_rejects_out_of_range(value: float) -> None:
    with pytest.raises(InvalidScore, match="outside the \\[0,1\\] output contract"):
        validate_score(value, function=FUNCTION)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_rejects_non_finite(value: float) -> None:
    with pytest.raises(InvalidScore, match="non-finite"):
        validate_score(value, function=FUNCTION)


@pytest.mark.parametrize("value", [True, False, "0.5", None])
def test_rejects_non_numbers(value: object) -> None:
    with pytest.raises(InvalidScore, match="not a real number"):
        validate_score(value, function=FUNCTION)


def test_error_names_the_offending_function_and_value() -> None:
    with pytest.raises(InvalidScore) as exc:
        validate_score(1.7, function=FUNCTION)
    message = str(exc.value)
    assert "team-fn" in message
    assert "v7" in message
    assert "1.7" in message
