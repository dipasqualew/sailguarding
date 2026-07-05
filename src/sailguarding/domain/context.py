"""The context a unit of work runs in.

Context is an **open set of typed dimensions**, never a fixed schema, so the model
generalises past software. Software runs carry ``{team, repo, environment, service}``;
a sofa purchase carries ``{home, room, budget_holder}``. Nothing here knows or cares
which dimensions it holds.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping

# JSON-scalar dimension values. ``bool`` is a subclass of ``int`` and is allowed on
# purpose (e.g. ``is_production=True``).
DimensionValue = str | int | float | bool


class Context(Mapping[str, DimensionValue]):
    """An immutable bag of typed dimensions describing where an action runs.

    Behaves as a read-only mapping so callers can do ``ctx["repo"]`` and
    ``ctx.get("environment")``. Arbitrary string keys are accepted; there is no fixed
    dimension set.
    """

    __slots__ = ("_dimensions",)

    _dimensions: dict[str, DimensionValue]

    def __init__(
        self,
        dimensions: Mapping[str, DimensionValue] | None = None,
        /,
        **more: DimensionValue,
    ) -> None:
        merged: dict[str, DimensionValue] = {}
        if dimensions is not None:
            merged.update(dimensions)
        merged.update(more)

        for key, value in merged.items():
            if not isinstance(key, str):
                raise TypeError(f"Context dimension keys must be str, got {type(key).__name__!r}")
            # Order matters: bool passes the (bool | int) check first and is intentional.
            if not isinstance(value, (str, int, float, bool)):
                raise TypeError(
                    f"Context dimension {key!r} must be a JSON scalar "
                    f"(str/int/float/bool), got {type(value).__name__!r}"
                )

        self._dimensions = merged

    def __getitem__(self, key: str) -> DimensionValue:
        return self._dimensions[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._dimensions)

    def __len__(self) -> int:
        return len(self._dimensions)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Context):
            return self._dimensions == other._dimensions
        return NotImplemented

    def __hash__(self) -> int:
        return hash(tuple(sorted(self._dimensions.items())))

    def __repr__(self) -> str:
        return f"Context({self._dimensions!r})"
