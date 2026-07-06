# 08 — Evidence ingestion & safeguard measurement

**Status:** done
**Depends on:** 02, 06

## Context

This is the **feature substrate** — the platform's half of the MLOps division of labour. The
safeguarding team declared *what* each safeguard measures and *which kind* (task 06); the operating
team wires the real metric sources (CI, test runners, git history for reverts/hotfixes, later incident
tooling). This task ingests that evidence and turns it into the **current signal** for each safeguard,
over time — the number task 09 will assemble into a feature vector.

Two SPEC constraints are load-bearing here:

- **The event log is not the metrics.** Git is a fine append-only log and a terrible time-series
  database. Derived safeguard metrics live behind a **separate, pluggable metrics sink** — explicitly
  *not* the branch/event-log storage from task 02. This task must not extend that seam.
- **Health is not efficacy, ever.** Health (flakiness, coverage delta, CI latency) is cheap, leading,
  and a proxy; efficacy (`P(catch | actually bad)`, back-tested against outcomes) is the lagging
  number that matters. The API keeps the two distinct and never lets one be read as the other.

## Scope

- **`Evidence` record:** one measurement for a safeguard — safeguard id, metric, value, **kind
  (health / efficacy)**, the context it was measured in, and a timestamp. Versioned, serializable,
  round-trip tested.
- **Metrics sink:** a pluggable append/query seam for evidence with an in-memory default, separate
  from the event-log storage of task 02.
- **Signal derivation:** compute a safeguard's *current* signal from its evidence history, keeping
  health and efficacy as separate series that are never conflated.

## Out of scope

- **Calibration** — moving the scoring function against outcomes (does 0.9-with-flakiness-X actually
  fail more?) is a later task; this task ingests and summarises evidence, it does not re-fit the
  function.
- **Assembling the feature vector** and running the scorer (task 09).
- **Specific metric adapters** (a real CI or git-history source) — the seam and one worked in-memory
  source are enough; production adapters are the operating team's wiring.

## Acceptance criteria

- `Evidence` is versioned, serializable, round-trip tested, and lands in a metrics sink that is
  distinct from the event-log storage.
- Health and efficacy are represented and queryable as separate series; no API path returns one where
  the other was asked for.
- A safeguard's latest signal is derivable from its ingested evidence history.
- The metrics sink is injected with an in-memory default; tests ingest and read back with no I/O.

## Demo

Replace the demo's manual sliders with **health/efficacy sparklines**: ingest a few evidence points
for a safeguard and watch its signal — and therefore its ceiling on the delegation float — move over
time. The panel shows health and efficacy as two clearly-labelled series, making the "never conflate
them" rule visible, not just asserted.

## Notes

- Evidence is joined to actions *after the fact*; keep it a separate stream from the pre-tool-use
  event log (which has no outcome), exactly as the SPEC's architecture section requires.
- Keep it domain-agnostic: "revert rate" for code and "return rate" for a purchase are the same shape.
