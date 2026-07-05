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

## Scope

- **Claude Code plugin + pre-tool-use hook** that, on each tool call, builds an `EventRecord`:
  - raw tool name and tool input,
  - resolved `Context` (at minimum repo and git branch; team/environment where available),
  - session id, timestamp, harness id (`claude-code`), schema version.
- The hook shells into a thin **engine CLI entrypoint** that writes the record through the
  `StorageStrategy` from task 02 (branch sink by default). Keep the hook itself thin; logic lives in
  the engine.
- **Non-blocking and fail-open as a sensor:** if the engine errors or is slow, the tool call must
  still proceed — a sensor must never break the user's agent session. (Enforcement will change this
  posture deliberately; recording must not.)
- **Install/enable path** as an idempotent script, not documentation.

## Out of scope

- Enforcement / blocking / gating (future; the actuator role of this same hook).
- Classification — records are written with `action_id` null; task 04 resolves them.
- Post-tool-use / outcome capture (evidence ingestion is a later task).

## Acceptance criteria

- Running a real Claude Code session with the plugin enabled produces `EventRecord`s in the branch
  sink for each tool call, with tool name, input, and context populated.
- Injecting the in-memory sink lets the sensor path be tested without a live session or a git branch.
- A forced engine failure does **not** interrupt the tool call (fail-open verified by test).
- Enable/disable is idempotent and leaves no residue when disabled.

## Notes

- Record enough of the tool input for task 04's selectors to match on (file paths, command strings),
  but define a redaction seam now — some tool inputs will contain secrets, and teams will need to
  configure what is stored.
