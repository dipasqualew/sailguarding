# 12 — Dashboard: requested → attested → holding → expired

**Status:** todo
**Depends on:** 09, 10, 11

## Context

The reframing is only real when a team can *see* it. The current dashboard tells a bounded-tool story
(write-tests, flakiness sliders); this task retells the standing demo around a **capability tool** and
the **freshness contract**, so the whole lifecycle — a safeguard requested, attested, holding, and
expiring — is on one screen and drivable.

This is the demo surface that ties the previous three tasks to the CLAUDE.md definition of done: each
of their acceptance criteria becomes something the user can watch happen.

## Scope

- **A capability panel for Bash:** the worst-case sentence (task 11), the reachable-authority
  inventory, and the current delegation float as the min over holding structural safeguards.
- **The lifecycle per safeguard:** for each *requested* safeguard show its state — **requested**
  (never attested), **holding** (fresh), or **expired** (stale) — with the **countdown to expiry** and
  the reasoning from its last attestation.
- **Drive it live:** an "attest" control that posts through the task-10 API and updates the panel; the
  demo clock control from task 09 to advance time past a window and watch a safeguard expire and the
  float fall.
- **Keep the bounded story too** where it still teaches (health/efficacy never conflated) — this
  reframes the demo, it does not delete what tasks 06–09 already proved.

## Out of scope

- **New engine behaviour** — this task is a *view* over tasks 09–11; any missing engine capability is a
  bug in those tasks, fixed there, not patched in the web layer.
- **Auth / multi-team** — enterprise, later.

## Acceptance criteria

- The dashboard renders a Bash capability panel showing the worst-case impact, the requested structural
  safeguards, their per-safeguard lifecycle state, and the resulting float — all from the real engine,
  no mock.
- Attesting a requested safeguard (via the panel control → task-10 API) moves it to **holding**, resets
  its countdown, and raises the float in the same view.
- Advancing the demo clock past a window moves a safeguard to **expired**, drops its ceiling to the
  caution floor, and lowers the float — nothing else changed.
- Each acceptance criterion of tasks 09, 10, and 11 is exercised by a visible interaction in this demo,
  so "done" for the reframing is observable end to end.

## Demo

This task *is* the demo. Capture the running dashboard: request → attest → holding (float up) →
advance clock → expired (float down) → re-attest (float recovers), for the Bash capability. Send the
user the capture (screenshots or a short recording), tied back to the lifecycle in the SPEC's
*requested, attested, holding, expired* section.

## Notes

- Follow the existing `web/` conventions: pure `App.handle` router, `scenario.py` wiring the real
  engine, page rendered server-side, zero runtime deps.
- The panel reads the same sink the ingestion API writes, so the demo is the genuine loop.
