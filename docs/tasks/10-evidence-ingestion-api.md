# 10 — The evidence ingestion API

**Status:** todo
**Depends on:** 09

## Context

Attestations have to get *in*. The freshness contract (task 09) is inert without a way for the
operating team to post evidence on the cadence — "ephemeral envs verified for `repo=X`, valid one
week, here's why." The SPEC's architecture section calls this out: ingestion is an **API**, not only a
scraper. A human posting a structural claim and a CI job posting a metric are the same shape landing
through the same door.

This task builds that door and wires it into the standing demo surface (`sg serve`), reusing the
zero-dependency, testable-router pattern already in `src/sailguarding/web/`.

## Scope

- **An ingestion endpoint:** accept an attestation — safeguard id, context, the attested value **or**
  a structural claim, the **reasoning**, and enough to derive the validity window (the measurement
  time; the cadence comes from the safeguard). Lands it in the metrics sink from task 08. Keep it a
  pure `(request) -> response` handler behind the existing `App.handle` seam so tests never open a
  socket.
- **Validation that fails safe:** an attestation for an unknown safeguard, a malformed body, or a
  missing reasoning is **rejected** with a clear error — a bad attestation must never silently become
  allowance.
- **A CLI verb** (e.g. `sg attest`) as the human/automation entry point, posting to the same handler,
  so the operating team can renew a safeguard from a shell or a CI step.

## Out of scope

- **Auth / who-may-attest** — the independent-validation workflow (validator ≠ author) is enterprise
  and later; this task ingests, it does not authorise.
- **Freshness derivation** — computing whether the posted evidence is fresh is task 09's; this task
  only lands it.
- **Applying it to Bash** — task 11 seeds the capability safeguards this API will renew.

## Acceptance criteria

- A valid attestation POSTed through the handler appears as `Evidence` in the sink and immediately
  becomes the safeguard's current signal (subject to task 09's freshness gate).
- A structural attestation with no numeric value is accepted; a metric attestation is accepted;
  neither path can be read back as the other's kind (health/efficacy separation holds end to end).
- Unknown safeguard id, malformed body, and missing reasoning each return a distinct, non-2xx error
  and land **nothing** in the sink.
- `sg attest` posts through the exact same handler the HTTP route uses — one code path, two front
  doors — and tests exercise the handler directly with no network.

## Demo

From the dashboard (or `sg attest` in a terminal captured alongside), **renew a safeguard live**: post
an attestation and watch its expiry countdown reset and the delegation float recover in the same view.
Then let it lapse and post a *stale-dated* one — rejected or shown as already-expired — proving the
door only opens for fresh, well-formed evidence.

## Notes

- Reuse `scenario.py`'s real engine wiring; the API mutates the same sink the panels read, so the demo
  is the genuine loop, not a parallel mock.
- Body shape should be domain-agnostic and match the `Evidence` serialisation from task 09 so a posted
  payload and a stored record are the same canonical JSON.
