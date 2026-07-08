# 09 — Attestation & the freshness contract

**Status:** done
**Depends on:** 06, 08

## Context

Delegation is a **subscription, not a one-time purchase**. A safeguard the operating team proved last
month tells you nothing today; the SPEC's design principle 1 ("autonomy decays when safeguards do")
only bites if evidence can go *stale*. This task gives evidence a shelf life.

The safeguarding team **requests** a safeguard and sets its **cadence** — how often it must be
re-evidenced (weekly, per-release). The operating team **attests**: it posts evidence carrying its
**reasoning** and a **validity window** derived from that cadence. Fresh evidence buys allowance for
exactly one window; once it lapses the safeguard stops holding and its signal fails toward caution.

This task changes the *model and the derivation together* — they are meaningless apart. It does not
add the ingestion API (task 10) or apply any of it to Bash (task 11).

## Scope

- **Cadence on `Safeguard`:** a renewal interval the safeguarding team declares (e.g. 7 days), or
  `None` for a safeguard that never expires. Versioned bump; round-trip stable.
- **Attestation fields on `Evidence`:** the **reasoning** (free text — how the operating team knows
  the control holds) and the **validity window**. Prefer deriving `expires_at` from the measurement
  timestamp + the safeguard's cadence over storing a redundant field, but store what round-trips
  cleanly. A non-metric attestation (a structural claim with no number) must be representable, not
  only a float.
- **Freshness-gated signal derivation:** `latest_signal` (and the series helpers) become
  freshness-aware against a "now". Evidence outside its window is **stale** and contributes **no
  signal**, so a safeguard with only stale evidence is indistinguishable from an unmet one — it fails
  toward caution.

## Out of scope

- **The ingestion API** — posting attestations over HTTP/CLI is task 10.
- **Capability modelling** — seeding Bash and its structural safeguards is task 11.
- **The decay *shape*** — this task implements a **cliff at expiry** (fresh → holds, expired →
  nothing). A ramp as the window runs down is open question #6, deferred.

## Acceptance criteria

- `Safeguard` carries an optional cadence, is versioned, and round-trips (`from_json(to_json()) ==`).
- `Evidence` carries reasoning and a validity window, round-trips, and can represent a structural
  attestation that has no numeric metric.
- Given an injected "now", signal derivation returns a safeguard's signal only from **unexpired**
  evidence; a safeguard whose newest evidence has expired derives no signal.
- A safeguard with only stale evidence produces the same (caution) outcome as one with no evidence at
  all — proven by test, not asserted.
- The metrics sink seam and health/efficacy separation from task 08 are unchanged.

## Demo

Extend the evidence panel: an attested safeguard shows its **countdown to expiry**. Advance the demo
clock past the window and the same evidence goes stale — its ceiling on the delegation float drops to
the caution floor, and the float visibly falls, with nothing else changed. "Renew" it (a fresh point)
and the float recovers. The subscription made visible.

## Notes

- "Now" must be **injected**, never `datetime.now()` reached for inside derivation — tests advance a
  fake clock to cross the boundary deterministically.
- Keep it domain-agnostic: an attestation of "ephemeral envs verified" and one of "return rate ≤ 2%"
  are the same shape with the same shelf life.
