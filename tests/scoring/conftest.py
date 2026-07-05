"""Shared fixtures for the scoring tests."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from sailguarding.scoring import FeatureVector


class StubScoringFunction:
    """A fixed-output :class:`ScoringFunction` — proves the platform runs without a real model.

    Returns whatever value it was constructed with, unvalidated, so tests can drive both the happy
    path and the output-contract rejection path (e.g. ``StubScoringFunction(1.7)``).
    """

    def __init__(self, value: object, *, name: str = "stub", version: str = "0") -> None:
        self._value = value
        self.name = name
        self.version = version

    def score(self, features: FeatureVector) -> float:
        return self._value  # type: ignore[return-value]  # deliberately unchecked for reject tests


StubFactory = Callable[..., StubScoringFunction]


@pytest.fixture
def make_function() -> StubFactory:
    """Build a :class:`StubScoringFunction` returning a fixed value."""

    def _make(value: object, *, name: str = "stub", version: str = "0") -> StubScoringFunction:
        return StubScoringFunction(value, name=name, version=version)

    return _make
