# 0001 — Python for the engine core

**Status:** accepted
**Date:** 2026-07-05

## Context

sailguarding executes team-authored **scoring functions** in the team's own environment
(see [`../../SPEC.md`](../../SPEC.md), "delegation float and behaviour bands"). Those functions are
real code the safeguarding team owns as IP, and the SPEC's worked examples — ceilings, `min`
composition, learned classifiers — are Python. The engine also assembles the feature substrate those
functions consume.

If the substrate and the models it runs live in different runtimes, every scoring function crosses a
serialization boundary and teams write their IP in a second language. A single-language core keeps the
substrate and the models in one runtime.

## Decision

The engine core is **Python** (`>=3.11`).

Tooling, chosen for zero-config idempotency (`./setup.sh`) and a single CI gate:

- **Environment / dependencies:** `uv` — fast, lockfile-based, reproducible.
- **Lint + format:** `ruff` (`ruff check`, `ruff format`).
- **Type-check:** `mypy --strict`. The domain types are the contract every downstream task imports;
  strict typing keeps that contract honest.
- **Tests:** `pytest`.
- **CI:** GitHub Actions runs lint + format-check + type-check + tests on push and PR across the
  supported Python versions.

Domain types are modelled with stdlib `dataclasses` (no ORM/validation framework) so the canonical
JSON encoding is owned explicitly rather than inherited from a library, and so the core has no runtime
dependencies.

## Consequences

- Scoring functions, feature substrate, and engine share one runtime and one serialization model.
- No runtime dependencies in the core package; dependencies are additive per later task.
- `3.11` is the floor: it gives `datetime.fromisoformat` full ISO-8601 (incl. `Z`) parsing, which the
  canonical `EventRecord` encoding relies on.
