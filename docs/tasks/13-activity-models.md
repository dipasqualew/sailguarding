# 13 — Activity models: a workspace of scoped, importable models

**Status:** done
**Depends on:** 06, 07

## Context

Until now the engine held exactly **one** governance aggregate (`ActivityModel` — a tree of
activities with a reusable risk library, safeguard library, and the edges between them), and the
store and dashboard opened onto that single model. A real organisation runs several models that do
not overlap, or only partly: a "Sales" model, a "Product Software Engineering" model, a "Platform
Software Engineering" model. Each governs a different slice of the work and a different slice of
context.

This task promotes "one model" to "a **workspace** of models". Each model gains an identity, a
human name, and — crucially — a declared **region of context it applies to** (e.g. `repo ∈
{checkout, billing}`), so a reader can tell which model governs which context. A person navigates
between models, scopes each one, and **imports** an activity, risk, or safeguard from one model into
another by copying (the source is left untouched), which is what makes partially-overlapping models
practical to maintain.

## Scope

- **`ContextScope`** (`model/scope.py`): a user-friendly `dimension → allowed values` predicate
  (`repo ∈ {checkout, billing}`), versioned/serialisable/round-trip stable, with pure editing
  transforms. An empty scope applies everywhere; an empty value-set means "has this dimension, any
  value". `matches(context)` decides whether a model governs a given `Context`.
- **`ActivityModel` schema v2**: adds `id`, `name`, and `applies_when: ContextScope`, with
  `set_name` / `set_applies_when` transforms. A v1 record still reads (defaults applied) and
  re-emits at v2. Adds **import primitives** — `import_risk` / `import_safeguard` (dedupe by id) and
  `import_activity` (copies the subtree with fresh activity ids, *and* the risks/safeguards it
  references plus the edges, so it lands governed). The source model is never mutated.
- **`Workspace`** (`model/workspace.py`): a versioned, serialisable collection of models with a
  remembered active model. Pure transforms to add/rename/remove/select/replace a model and to
  `import_into` one model from another.
- **`WorkspaceStore`** (`model/store.py`): the same save/load contract as the model store, with an
  in-memory default and an atomic `FileWorkspaceStore` (`workspace.json`).
- **Web app + dashboard**: the app holds a workspace; `/api/model/*` routes create/rename/delete/
  select a model, set its scope, and import between models; the activity/risk/safeguard routes act
  on the active model. The dashboard grows a **model switcher**, an editable **"applies when"**
  strip, and an **import dialog**.

## Out of scope

- **Routing live events to a model** — using `ContextScope.matches` in classification/scoring to
  pick which model governs an observed event. This task defines and edits the scope and navigation;
  wiring it into the observe→classify path is a follow-up.
- **Migrating an existing on-disk `model.json`** into the new `workspace.json` — demo state; a fresh
  seed is acceptable.
- **RBAC / multi-user / per-model permissions** (enterprise).

## Acceptance criteria

- A `Workspace` holds several `ActivityModel`s, tracks the active one, and is
  serialisable/round-trip tested; each model carries an id, a name, and an `applies_when` scope.
- `ContextScope` matches a context by `dimension → allowed values`, is user-legible
  (`describe()`), editable through pure transforms, and round-trip tested.
- An activity/risk/safeguard can be **imported** from one model into another by copying, leaving the
  source unchanged; importing an activity brings its risks, safeguards, and edges.
- Stores are injected with in-memory defaults; a fresh workspace drives tests with no I/O. A v1
  model record still loads.

## Demo

A **model switcher** across the top of the dashboard (`sg serve`): navigate between "Product
Software Engineering", "Platform Software Engineering", and "Sales". Each shows its **"applies
when"** strip — edit Product's to add a repo and watch the scope summary update. Use **Import from
another model…** to copy "Provision infrastructure" from Platform into Product, and confirm it
arrives with its risks and safeguards (and that the shared "Ephemeral environments" safeguard
dedupes rather than duplicating). Create a fresh empty model from the switcher. Each step exercises
one acceptance criterion, so "done" is observable in the running app.

## Notes

- Keep everything domain-agnostic: a `ContextScope` scopes `repo ∈ {checkout}` exactly as it scopes
  `room ∈ {living, kitchen}`; the same import machinery moves a code activity or a purchasing one.
- `ContextScope` is deliberately friendlier than the classification `Selector` (one dimension → a
  *list* of options, not a single glob) because it is edited by a person and rendered as value
  chips. The two stay separate on purpose.
