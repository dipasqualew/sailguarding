# 01 — Scaffold and event schema

**Status:** done
**Depends on:** —

## Context

This is the foundation every other task imports from. sailguarding observes what an agent does,
resolves each observation to an **action** in a **context**, and reasons about it. Before any of that
can happen we need the project skeleton and the core data types — above all the **event record**, the
append-only unit the sensor writes and everything downstream reads.

The event record is deliberately domain-agnostic: it must describe "a tool wrote to a file in this
repo" and, unchanged, "an agent placed an order for this home." First use case is software, but the
schema must not bake software in.

## Scope

- **Stack decision.** Default to **Python** for the engine — the scoring functions teams author are
  Python (see SPEC), so a single-language core keeps the substrate and the models in one runtime.
  Record the decision and its rationale in the repo.
- **Project scaffolding:** package layout, dependency management, lint, formatter, type-checking, a
  test runner, and a CI workflow that runs them. Provide an idempotent `setup` script (per the
  "executable tools over docs" principle) rather than setup prose.
- **Core domain types:**
  - `Context` — an open bag of typed dimensions (`{team, repo, environment, ...}`), not a fixed
    schema. Must support arbitrary keys so non-software domains fit.
  - `Action` — the recursive unit: id, optional parent, human label, children. Root = "goal", leaf =
    an undecomposed task. One type, not two.
  - `EventRecord` — the append-only observation: timestamp, session id, harness id, raw tool name +
    input, resolved context, and a nullable `action_id` (unresolved at capture time; filled by
    classification later). Include a schema version field.
- **Serialization:** a single canonical JSON encoding for `EventRecord` (this is what task 02 writes
  as JSONL). Round-trip tested.

## Out of scope

- Storage backends (task 02).
- The Claude Code hook (task 03).
- Classification / selectors (task 04).
- Safeguards, scoring, budgets (task 05+).

## Acceptance criteria

- `setup` script brings a clean machine to a state where lint, type-check, and tests pass.
- CI runs lint + type-check + tests on push.
- `Context`, `Action`, `EventRecord` types exist with tests, including an `Action` tree with children
  and a `Context` carrying non-software dimensions (e.g. a sofa example) to prove domain-agnosticism.
- `EventRecord` serializes to canonical JSON and round-trips losslessly, with the schema version
  present.

## Notes

- Keep `action_id` nullable on `EventRecord` on purpose: the sensor captures before classification
  runs, and outcomes/joins happen later. Do not force resolution at capture time.
