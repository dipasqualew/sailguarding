# 05 — Scoring-function contract

**Status:** done
**Depends on:** 01, 04

## Context

This is the platform's central API (SPEC open question #1). sailguarding never computes the
delegation float itself — **the scoring function is the safeguarding team's IP**. The platform's job
is to assemble the inputs, execute the team's function, and log the decision. Get this contract right
and everything downstream (safeguards, calibration, enforcement) has something stable to build on;
get it wrong and it all churns.

Three pieces define the contract: the **feature vector** the platform assembles, the **function
signature** the team implements, and the **decision log** that makes every score auditable.

## Scope

- **Feature vector schema:** the typed input the platform assembles for an `(action, context)` — the
  measured signals from each bound safeguard, the context dimensions, and remaining budget. Must be
  versioned and serializable (it is logged with every decision). For this task, signals can be
  supplied directly (no live ingestion yet); the schema is what matters.
- **`ScoringFunction` interface:** `features → float in [0,1]`. Team-authored Python. The platform
  executes it; it does not constrain its internals. Validate only the **output contract** (finite,
  within `[0,1]`); reject out-of-range results loudly.
- **Decision log:** for every score, persist inputs (the feature vector), the function identity +
  **version**, the output float, and a timestamp — so "why was this delegated at 0.9?" is answerable
  months later. This is model risk management pointed at the scorer (SR 11-7).
- **Worked example — `min`-composition:** a reference scoring function where each safeguard maps its
  metric to a ceiling and the float is the binding minimum. Ship it as a *library example*, explicitly
  not as a framework rule — it demonstrates the compositional pattern and proves the contract.
- **Two guarantees the reference example must show** (and that the contract should make easy to honor):
  impact caps hard (a catastrophic input ceilings low regardless of other signals), and remaining
  budget pulls the float down toward the human.

## Out of scope

- Live evidence ingestion and calibration (later task) — signals are supplied for now.
- Behaviour bands + enforcement (later) — this task stops at producing and logging the float.
- ML/LLM scorers and their execution model (open question #2: caching, latency, fallback) — the
  interface must *allow* them, but this task ships the in-process example only.

## Acceptance criteria

- Feature-vector schema is versioned, serializable, and round-trip tested.
- A team-supplied function is executed against a feature vector and returns a float; out-of-range or
  non-finite outputs are rejected with a clear error.
- Every score writes a decision-log entry containing inputs, function version, output, timestamp;
  reading it back reproduces the decision inputs exactly.
- The `min`-composition example demonstrates impact-caps-hard and budget-pulls-down in tests.
- The scoring function is injected; a stub function is usable in tests without any real risk model.

## Notes

- Do **not** enforce input→output monotonicity at the platform level — an arbitrary team function
  (e.g. an LLM classifier) cannot guarantee it. Monotonicity is a property a team may choose to
  validate about its own function; the platform only enforces the `[0,1]` output contract.
- The scorer runs **in the team's environment** and its code/signals are IP — keep the execution seam
  local and injectable, never a call out to a vendor service.
