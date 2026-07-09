"""The :class:`ContextScope` and :class:`DimensionConstraint`: matching, describing, transforms.

Every test builds a fresh scope in-memory; nothing touches the filesystem.
"""

from __future__ import annotations

import pytest

from sailguarding.model import SCOPE_SCHEMA_VERSION, ContextScope, DimensionConstraint

# -- DimensionConstraint ----------------------------------------------------------------------


def test_constraint_allows_any_value_when_values_empty() -> None:
    constraint = DimensionConstraint(name="repo")
    assert constraint.allows("checkout")
    assert constraint.allows("anything")


def test_constraint_allows_only_listed_values() -> None:
    constraint = DimensionConstraint(name="repo", values=("checkout", "billing"))
    assert constraint.allows("checkout")
    assert not constraint.allows("infra")


def test_constraint_stringifies_the_value_before_membership() -> None:
    constraint = DimensionConstraint(name="attempt", values=("2",))
    assert constraint.allows(2)  # the int is stringified to "2"
    assert not constraint.allows(3)


def test_constraint_describe_bare_one_and_many() -> None:
    assert DimensionConstraint(name="repo").describe() == "repo"
    assert DimensionConstraint(name="repo", values=("checkout",)).describe() == "repo = checkout"
    assert (
        DimensionConstraint(name="repo", values=("checkout", "billing")).describe()
        == "repo ∈ {checkout, billing}"
    )


def test_constraint_round_trips_through_dict() -> None:
    constraint = DimensionConstraint(name="repo", values=("checkout", "billing"))
    assert DimensionConstraint.from_dict(constraint.to_dict()) == constraint


def test_constraint_from_dict_defaults_missing_values_to_empty() -> None:
    assert DimensionConstraint.from_dict({"name": "repo"}) == DimensionConstraint(name="repo")


# -- ContextScope.matches ---------------------------------------------------------------------


def test_empty_scope_matches_everything() -> None:
    scope = ContextScope.empty()
    assert scope.matches({})
    assert scope.matches({"repo": "checkout"})


def test_empty_values_constraint_matches_any_context_that_has_the_dimension() -> None:
    scope = ContextScope.empty().set_dimension("repo", ())
    assert scope.matches({"repo": "checkout"})
    assert scope.matches({"repo": "anything"})
    assert not scope.matches({"team": "sales"})  # missing the dimension entirely


def test_value_must_be_in_the_allowed_set() -> None:
    scope = ContextScope.empty().set_dimension("repo", ("checkout", "billing"))
    assert scope.matches({"repo": "checkout"})
    assert not scope.matches({"repo": "infra"})


def test_missing_dimension_fails_the_match() -> None:
    scope = ContextScope.empty().set_dimension("repo", ("checkout",))
    assert not scope.matches({"team": "sales"})


def test_all_constraints_must_hold() -> None:
    scope = (
        ContextScope.empty()
        .set_dimension("repo", ("checkout",))
        .set_dimension("environment", ("staging",))
    )
    assert scope.matches({"repo": "checkout", "environment": "staging"})
    assert not scope.matches({"repo": "checkout", "environment": "production"})
    assert not scope.matches({"repo": "checkout"})  # missing the second dimension


def test_matches_stringifies_non_string_context_values() -> None:
    scope = ContextScope.empty().set_dimension("attempt", ("2",))
    assert scope.matches({"attempt": 2})  # int 2 stringified to "2"
    assert not scope.matches({"attempt": 3})


# -- ContextScope.describe --------------------------------------------------------------------


def test_describe_empty_scope_applies_everywhere() -> None:
    assert ContextScope.empty().describe() == "applies everywhere"


def test_describe_joins_constraints_with_semicolons() -> None:
    scope = (
        ContextScope.empty()
        .set_dimension("repo", ("checkout", "billing"))
        .set_dimension("environment", ("staging",))
    )
    assert scope.describe() == "repo ∈ {checkout, billing}; environment = staging"


# -- ContextScope.set_dimension ---------------------------------------------------------------


def test_set_dimension_appends_a_new_dimension() -> None:
    scope = ContextScope.empty().set_dimension("repo", ("checkout",))
    scope = scope.set_dimension("team", ("sales",))
    assert [c.name for c in scope.dimensions] == ["repo", "team"]


def test_set_dimension_replaces_in_place_keeping_position() -> None:
    scope = (
        ContextScope.empty().set_dimension("repo", ("checkout",)).set_dimension("team", ("sales",))
    )
    updated = scope.set_dimension("repo", ("billing",))
    # repo keeps its leading position; only its values change.
    assert [c.name for c in updated.dimensions] == ["repo", "team"]
    assert updated.dimensions[0].values == ("billing",)


def test_set_dimension_dedupes_values_preserving_order() -> None:
    scope = ContextScope.empty().set_dimension("repo", ("checkout", "billing", "checkout"))
    assert scope.dimensions[0].values == ("checkout", "billing")


def test_set_dimension_stringifies_values() -> None:
    scope = ContextScope.empty().set_dimension("attempt", (1, 2, 2))  # type: ignore[arg-type]
    assert scope.dimensions[0].values == ("1", "2")


def test_set_dimension_is_pure() -> None:
    original = ContextScope.empty()
    grown = original.set_dimension("repo", ("checkout",))
    assert original.dimensions == ()  # receiver untouched
    assert grown.dimensions != ()


# -- ContextScope.remove_dimension ------------------------------------------------------------


def test_remove_dimension_drops_the_named_constraint() -> None:
    scope = (
        ContextScope.empty().set_dimension("repo", ("checkout",)).set_dimension("team", ("sales",))
    )
    updated = scope.remove_dimension("repo")
    assert [c.name for c in updated.dimensions] == ["team"]


def test_remove_dimension_absent_is_a_noop() -> None:
    scope = ContextScope.empty().set_dimension("repo", ("checkout",))
    assert scope.remove_dimension("team") == scope


# -- serialisation ----------------------------------------------------------------------------


def test_round_trips_through_dict() -> None:
    scope = (
        ContextScope.empty()
        .set_dimension("repo", ("checkout", "billing"))
        .set_dimension("environment", ())
    )
    assert ContextScope.from_dict(scope.to_dict()) == scope


def test_empty_scope_round_trips() -> None:
    assert ContextScope.from_dict(ContextScope.empty().to_dict()) == ContextScope.empty()


def test_serialised_form_is_versioned() -> None:
    assert ContextScope.empty().to_dict()["schema_version"] == SCOPE_SCHEMA_VERSION


def test_rejects_unknown_schema_version() -> None:
    data = ContextScope.empty().to_dict()
    data["schema_version"] = 999
    with pytest.raises(ValueError, match="unsupported ContextScope schema_version"):
        ContextScope.from_dict(data)
