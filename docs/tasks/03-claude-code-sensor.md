# 03 — Claude Code sensor

**Status:** todo
**Depends on:** 01, 02

## Context

The first harness we support is Claude Code, and the integration point is a **pre-tool-use hook**.
The hook is a **sensor now** (record what the agent is about to do) and the **actuator later** (gate
the action against a behaviour band). Building on this exact hook is what makes enforcement an
additive step rather than a rewrite — so capture the shape well now.

Pre-tool-use fires **before** execution, so it sees *what the agent intends to do*, not whether it
worked. This task captures the intent. Outcomes/evidence arrive through a separate ingestion later and
are joined to the action stream then. Do not try to capture success here.

### Save trigger and the unit of work

The hook fires **per tool call**, so the natural save is one `EventRecord` per tool call — the finest
grain, captured before execution. But a single tool call is too small to *judge*: safeguards produce a
score in `[0, 1]`, and to ask "was that the right call?" you need an outcome attached to a coherent
**unit of work**, not to an isolated `Edit`. The candidate boundary is a **git commit**: it groups a
run of tool calls into one reviewable, revertable, outcome-bearing artifact — it lands or is reverted,
CI passes or fails.

Capturing that outcome and computing effectiveness is a later task (evidence ingestion + scoring). What
this task must not skip is the **correlation seam**: capture enough now so those later tasks can group
per-tool-call events into the commit-sized unit they contributed to, and score the safeguard against
that unit's outcome. Because `Context` is an open bag of dimensions (task 01), the work-unit key rides
along as context (e.g. the branch and HEAD commit at capture time) — **no schema change needed**. Design
this seam deliberately, like the redaction seam below; do not bake in a single definition of "unit of
work" (a commit is the first boundary, not the only one).

## Scope

- **Claude Code plugin + pre-tool-use hook** that, on each tool call, builds an `EventRecord`:
  - raw tool name and tool input,
  - resolved `Context` (at minimum repo and git branch; team/environment where available),
  - the **work-unit correlation key** (e.g. the HEAD commit at capture time) carried as a context
    dimension, so later tasks can attribute the event to the unit of work it lands in,
  - session id, timestamp, harness id (`claude-code`), schema version.
- The hook shells into a thin **engine CLI entrypoint** that writes the record through the
  `StorageStrategy` from task 02 (branch sink by default). Keep the hook itself thin; logic lives in
  the engine.
- **Non-blocking and fail-open as a sensor:** if the engine errors or is slow, the tool call must
  still proceed — a sensor must never break the user's agent session. (Enforcement will change this
  posture deliberately; recording must not.)
- **Marketplace:** ship a `.claude-plugin/marketplace.json` in this repo that lists the plugin, so it
  installs through Claude Code's plugin flow rather than hand-edited settings. The marketplace is
  **local to this repo**, not a published/hosted one — nothing is published externally and it stays
  offline-friendly like the rest of the design.
- **Install/enable/disable** as an idempotent script (per "executable tools over docs"): registers the
  local marketplace, installs and enables the plugin, and cleanly disables it leaving no residue.
- **Deterministic test harness (a Claude Code mock):** a stand-in that drives the plugin exactly the
  way Claude Code does — feeding a PreToolUse invocation through the same hook contract (tool name,
  tool input, session data on stdin/env as the real harness passes them). This is what lets the sensor
  path be exercised end-to-end, with the in-memory sink injected, deterministically and without a live
  agent session.

## Out of scope

- Enforcement / blocking / gating (future; the actuator role of this same hook).
- Classification — records are written with `action_id` null; task 04 resolves them.
- Post-tool-use / outcome capture (evidence ingestion is a later task).

## Acceptance criteria

- The plugin installs through the in-repo marketplace via Claude Code's plugin flow (not hand-edited
  settings); enable/disable is idempotent and leaves no residue when disabled.
- Running a real Claude Code session with the plugin enabled produces `EventRecord`s in the branch
  sink for each tool call, with tool name, input, and context populated.
- The Claude Code mock drives the hook **deterministically**: with the in-memory sink injected, the
  sensor path is exercised end-to-end and the captured `EventRecord` matches the simulated tool call —
  no live session or git branch required.
- Each captured record carries the work-unit correlation key (git branch/commit) needed to later join
  per-tool-call events into a unit of work for effectiveness scoring.
- A forced engine failure does **not** interrupt the tool call (fail-open verified by test).

## Notes

- Record enough of the tool input for task 04's selectors to match on (file paths, command strings),
  but define a redaction seam now — some tool inputs will contain secrets, and teams will need to
  configure what is stored.
- The mock is only as useful as its fidelity to Claude Code's real hook contract (how a PreToolUse
  hook receives tool name, tool input, and session data). Pin that contract explicitly so the mock and
  the plugin cannot silently drift from the real harness — confirm it against current Claude Code docs
  before building.
