"""Unit tests for :class:`sailguarding.domain.Context`.

Context must be domain-agnostic: it stores an open set of typed dimensions with no
fixed schema. We prove this by parameterising over a software context
(``team/repo/environment/service``) and a non-software "sofa" context
(``home/room/budget_holder``) that mixes str/int/float/bool values.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from sailguarding.domain import Context, DimensionValue

# A software delivery context and an unrelated "sofa purchase" context. The point is that
# the same type carries both without knowing which dimensions it holds, and that scalar
# types other than str (int/float/bool) are accepted.
SOFTWARE_DIMENSIONS: dict[str, DimensionValue] = {
    "team": "core",
    "repo": "checkout",
    "environment": "production",
    "service": "payments",
}
SOFA_DIMENSIONS: dict[str, DimensionValue] = {
    "home": "seaside-cottage",
    "room": "living-room",
    "budget_holder": "alex",
    "seats": 3,
    "price": 1299.99,
    "delivered": False,
}

DOMAIN_CASES = [
    pytest.param(SOFTWARE_DIMENSIONS, id="software"),
    pytest.param(SOFA_DIMENSIONS, id="sofa"),
]


@pytest.mark.parametrize("dimensions", DOMAIN_CASES)
def test_mapping_access(dimensions: dict[str, DimensionValue]) -> None:
    ctx = Context(dimensions)

    assert len(ctx) == len(dimensions)
    assert set(ctx) == set(dimensions)
    for key, value in dimensions.items():
        assert key in ctx
        assert ctx[key] == value
        assert ctx.get(key) == value

    assert "does-not-exist" not in ctx
    assert ctx.get("does-not-exist") is None
    assert ctx.get("does-not-exist", "fallback") == "fallback"
    assert dict(ctx) == dimensions


@pytest.mark.parametrize("dimensions", DOMAIN_CASES)
def test_missing_key_raises_keyerror(dimensions: dict[str, DimensionValue]) -> None:
    ctx = Context(dimensions)

    with pytest.raises(KeyError):
        _ = ctx["absent"]


def test_is_a_mapping() -> None:
    assert isinstance(Context(SOFTWARE_DIMENSIONS), Mapping)


def test_kwargs_construction() -> None:
    assert Context(repo="checkout", team="core") == Context({"repo": "checkout", "team": "core"})


def test_positional_and_kwargs_merge_with_kwargs_winning() -> None:
    ctx = Context({"repo": "checkout", "team": "core"}, team="platform")

    assert ctx["repo"] == "checkout"
    assert ctx["team"] == "platform"


def test_empty_context() -> None:
    ctx = Context()

    assert len(ctx) == 0
    assert dict(ctx) == {}


@pytest.mark.parametrize("dimensions", DOMAIN_CASES)
def test_equality_is_content_based(dimensions: dict[str, DimensionValue]) -> None:
    assert Context(dimensions) == Context(dict(dimensions))


def test_inequality_on_differing_content() -> None:
    assert Context(repo="checkout") != Context(repo="billing")


@pytest.mark.parametrize(
    "other",
    [
        pytest.param({"repo": "checkout"}, id="plain-dict"),
        pytest.param("checkout", id="str"),
        pytest.param(42, id="int"),
        pytest.param(None, id="none"),
    ],
)
def test_equality_only_against_context(other: object) -> None:
    # __eq__ returns NotImplemented for non-Context; Python falls back so the result is
    # simply "not equal" rather than an error.
    assert Context(repo="checkout") != other


@pytest.mark.parametrize("dimensions", DOMAIN_CASES)
def test_hash_is_order_independent(dimensions: dict[str, DimensionValue]) -> None:
    forward = Context(dimensions)
    reversed_items = dict(reversed(list(dimensions.items())))
    backward = Context(reversed_items)

    assert forward == backward
    assert hash(forward) == hash(backward)


@pytest.mark.parametrize("dimensions", DOMAIN_CASES)
def test_usable_as_dict_key_and_set_member(dimensions: dict[str, DimensionValue]) -> None:
    a = Context(dimensions)
    b = Context(dict(reversed(list(dimensions.items()))))

    # Equal contexts collapse to one entry regardless of construction order.
    assert len({a, b}) == 1
    lookup = {a: "value"}
    assert lookup[b] == "value"


def test_repr_is_context_shaped() -> None:
    text = repr(Context(repo="checkout"))

    assert text.startswith("Context(")
    assert "repo" in text
    assert "checkout" in text


@pytest.mark.parametrize(
    "bad_key",
    [
        pytest.param(1, id="int-key"),
        pytest.param(2.0, id="float-key"),
        pytest.param(("tuple",), id="tuple-key"),
    ],
)
def test_non_str_key_raises_type_error(bad_key: Any) -> None:
    with pytest.raises(TypeError):
        Context({bad_key: "value"})


@pytest.mark.parametrize(
    "bad_value",
    [
        pytest.param(["a", "list"], id="list"),
        pytest.param({"nested": "dict"}, id="dict"),
        pytest.param(("a", "tuple"), id="tuple"),
        pytest.param(None, id="none"),
        pytest.param(object(), id="object"),
    ],
)
def test_non_scalar_value_raises_type_error(bad_value: Any) -> None:
    with pytest.raises(TypeError):
        Context({"key": bad_value})


def test_bool_value_is_accepted() -> None:
    # bool is a JSON scalar (subclass of int) and must be allowed on purpose.
    ctx = Context(is_production=True)

    assert ctx["is_production"] is True
