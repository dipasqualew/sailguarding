# 10 — Behaviour bands & hysteresis

**Status:** todo
**Depends on:** 05

## Context

A delegation float in `[0,1]` is not yet an instruction. The safeguarding team maps it to **enforced
human+agent behaviour** — a band. For test writing: `0` = "I write the tests myself"; `0.5 < x < 1` =
"I review the tests the agent wrote"; `1` = "I don't look." This task turns the float into that band,
so the recommendation is actionable and, later (enforcement), gate-able.

Two requirements the SPEC pins on the banding, both about not lying to the operator:

- **Monotonic + partitioned.** Higher float always means more autonomy; the bands cover `[0,1]` with
  no gaps and no overlaps. A float always lands in exactly one band.
- **Hysteresis at boundaries.** The float wobbles run-to-run — flakiness *is* noise. The enforced band
  must not flap when the score hovers on a line: require the float to cross a boundary by a margin
  before the behaviour changes, given the band it is currently in.

## Scope

- **`BandMap`:** an ordered set of bands covering `[0,1]`, each with a label and the enforced
  behaviour it denotes. Construction validates monotonic + partitioned (rejecting gaps and overlaps).
  Versioned and serializable.
- **Resolution:** map a bare float to its band.
- **Hysteresis:** map a float *plus the previous band* to the next enforced band, holding the prior
  band until the float clears the boundary by a configured margin.

## Out of scope

- **Enforcement / the actuator** — gating the pre-tool-use hook per band is a later task; this task
  produces the band, it does not act on it.
- **Computing the float** (task 05) and assembling its inputs (task 09).

## Acceptance criteria

- A `BandMap` validates monotonic + partitioned coverage of `[0,1]` and rejects gaps/overlaps with a
  clear error; it is serializable and round-trip tested.
- A float resolves to exactly one band.
- Hysteresis holds: a float wobbling within the margin of a boundary keeps the previous band; crossing
  by the margin switches it. Both directions are tested.
- The band map is injected; a stub map drives tests.

## Demo

A **band strip** under the delegation float on the dashboard: the `[0,1]` axis shown partitioned into
labelled bands, with the current float and its band highlighted. Nudge the float across a boundary and
watch hysteresis **hold** the prior band until the margin is cleared, then switch — the anti-flap
behaviour made visible.

## Notes

- Bands are team-authored policy, not a framework constant — ship a worked example map (mirroring the
  SPEC's test-writing bands) as a *library example*, the way task 05 shipped the `min`-composition.
- Hysteresis needs the previous band as state; keep that state explicit and passed in, not hidden in
  the band map, so resolution stays pure and testable.
