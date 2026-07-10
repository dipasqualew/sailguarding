# CLAUDE.md

Guidance for working in this repository.

## What this is

sailguarding is a Python engine that models the work a team hands to agents, holds the
safeguards that make that handover safe, measures whether they hold, and computes a per-action
delegation recommendation. See [`SPEC.md`](SPEC.md) for the model and
[`docs/tasks/`](docs/tasks/) for the ordered units of work.

## Definition of done: every task ships a demo

**A task is not complete until it has been demonstrated to the user.** Passing tests, a green
type-check, and a clean diff are necessary but not sufficient — they prove the code runs, not that
it does what the story promised. Closing a task requires a **demo that proves the work is done up
to spec**: something the user can see and, ideally, drive.

Concretely, before marking a task done:

- Build or extend a **visible demo** of the new behaviour. The web dashboard
  (`sg serve`, see [`src/sailguarding/web/`](src/sailguarding/web/)) is the
  standing demo surface — most stories should add a panel or interaction to it rather than a
  one-off script.
- **Show it to the user**, not just describe it. In a remote/web session where the user cannot run
  the server themselves, drive the running app with the headless browser and send a screenshot (or
  a short capture) of the real thing. Curl output of the live API is acceptable supporting
  evidence, but the primary artifact is the demo itself.
- Tie the demo back to the task's **acceptance criteria** — the demo should exercise each one, so
  "done" is observable, not asserted.

Pick and sequence stories so they are demoable. A story whose result cannot be shown is either
mis-scoped or missing its demo surface — fix that as part of the story, not after.

## Conventions

- **Zero-dependency engine.** `pyproject.toml` keeps the `sailguarding` engine's
  `dependencies = []`; the core is stdlib-only. Dev tooling (ruff, mypy, pytest) lives in the `dev`
  group.
- **The front-end is a real React SPA.** It lives in [`frontend/`](frontend/) (Vite + React +
  TypeScript) and talks to the engine's JSON API. `npm run build` lands the bundle in
  `src/sailguarding/web/static/`, and `sg serve` serves it; `npm run dev` runs HMR against a live
  Python server (it proxies `/api`). The API base is configurable (`VITE_API_BASE`) so the SPA can
  later point at a separate hosted backend. (The old "stdlib-only, no build step" rule for the web
  surface is retired — Node is dev tooling, like ruff/mypy.)
- **The JSON API is the contract.** [`web/app.py`](src/sailguarding/web/app.py) is a framework-free
  `(method, path, query, body) -> Response` router over the real aggregates; the SPA is a genuine
  front-end over it, and it stays testable without a socket.
- **Pluggable seams, injected.** Storage, classification strategy, scoring function, and decision
  log are `Protocol`s with an in-memory default, so tests inject a fresh one per case with no I/O.
- **Serialisable, versioned, round-trip tested.** On-disk shapes carry a `schema_version` and a
  canonical JSON encoding; a record and its read-back must be equal.
- **Domain-agnostic core.** The same `Context` / `Action` / `EventRecord` describe a code edit and
  a sofa purchase. Keep new domain types free of software-specific assumptions.

## Checks

```
./setup.sh check      # ruff + ruff format + mypy + pytest, then front-end npm typecheck
```

Run this before committing. Everything must be green **and** the task's demo shown. `sg serve`
requires the front-end to be built (`./setup.sh` does this, or run `npm run build` in `frontend/`).
