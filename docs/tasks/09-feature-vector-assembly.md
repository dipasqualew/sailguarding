# 09 — Feature-vector assembly: close the recommend loop

**Status:** todo
**Depends on:** 05, 06, 07, 08

## Context

Task 05 shipped the scoring contract with signals **supplied directly** — a deliberate placeholder.
This task removes the placeholder and makes the platform do its actual job: for a real
`(action, context)`, **assemble** the feature vector from the governed pieces and execute the team's
function against it. It is the join that turns four separate seams into the SPEC's core loop —
`observe → classify → govern → measure → recommend` — running end to end on one event.

The division of labour holds: the platform owns the *assembly and execution*, the team owns the
*function*. Nothing here computes or prescribes the float; it gathers the inputs and logs the
decision.

## Scope

- **Assembler:** given an `(action, context)`, resolve the bound safeguards (task 06), pull each one's
  latest measured signal (task 08), resolve the remaining error budget (task 07), and build the
  `FeatureVector` (task 05).
- **End-to-end path:** wire a real event through classify (task 04) → assemble → score (task 05) →
  decision log, so a single observed event yields a logged delegation decision.
- **Fail toward caution:** a bound safeguard with no measured signal yet must not silently vanish — it
  assembles as an unproven input that earns no autonomy (the reference scorer already ceilings a
  missing signal to 0; the assembler must surface it, not drop it).

## Out of scope

- **Behaviour bands** (task 10) — this task stops at producing and logging the float.
- **The execution model for costly scorers** (open question #2: caching, latency budget, fallback) —
  the assembler runs the in-process function synchronously for now.
- **Calibration** of the function against outcomes (later).

## Acceptance criteria

- The assembler builds a `FeatureVector` for a given `(action, context)` from resolved bindings,
  measured signals, and the resolved budget — with no signals hand-fed.
- The full path observe → classify → assemble → score → log runs on a real event and writes one
  decision-log entry whose inputs reproduce the assembled vector exactly.
- A bound safeguard with no evidence yet is represented in the vector and drives the float toward the
  human (fail toward caution), never omitted.
- Every seam (registry, metrics sink, budget store, scorer, log) is injected; the whole loop runs
  in-memory in tests.

## Demo

On the dashboard, select an `(action, context)` from the tree and the **feature vector assembles
itself** — the manual sliders are replaced by "what the platform actually measured" (signals from
task 08, budget from task 07), and the delegation float appears from the real scorer. Ingesting new
evidence or changing a budget re-drives the float, showing the closed loop live.

## Notes

- This is where the demo dashboard graduates from a hand-driven scorer to a real recommendation
  surface; keep the manual-slider mode available as a "what-if" alongside the assembled view.
