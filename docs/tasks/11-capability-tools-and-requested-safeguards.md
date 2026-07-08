# 11 — Capability tools & requested structural safeguards

**Status:** todo
**Depends on:** 04, 06, 07, 09

## Context

This is where the reframing meets the engine. `Bash(X)` is a **capability tool**: it runs arbitrary
code at the host process's authority, so you do not govern it by parsing `X` — you **assume the
worst** and model the reachable authority (credentials, network, filesystem). Delegation on a
capability is not earned by a track record; it is **bought by structural safeguards that shrink that
authority**, each *requested* by the safeguarding team and *attested* by the operating team on a
cadence (task 09).

This task seeds that model as real engine data — one capability action and its requested structural
safeguards — so the `min`-composition scorer already in place produces a Bash delegation float that is
the weakest holding safeguard, and collapses when a structural attestation lapses.

## Scope

- **Bash as one action class:** classify the `Bash` tool to a single `arbitrary-host-execution` action
  (no command parsing), via the selector engine from task 04. Recognising the capability is the whole
  classification job here.
- **Requested structural safeguards, seeded and bound:** e.g. `ephemeral-environment`,
  `secrets-brokering`, `egress-allowlist`, `operation-audit` — each a `Safeguard` tagged
  **STRUCTURAL**, carrying a cadence (task 09), bound to `arbitrary-host-execution` in a context
  (`repo=X`) through the registry from task 06.
- **Worst-case impact for the capability:** an impact ceiling that caps hard when the reachable
  authority includes something catastrophic (e.g. production-write), so no amount of detection buys it
  back — SPEC design principle 4.
- **The composition already holds:** with the safeguards bound, the existing scorer yields the Bash
  float as the min over holding safeguards; an unattested (or expired) structural safeguard contributes
  its caution floor and ceilings the float low.

## Out of scope

- **A live host-authority scanner** — actually enumerating a machine's reachable credentials/network is
  the operating team's wiring and a later task; seed the inventory as declared context here.
- **Enforcement** — gating the Bash call on the float is the future actuator, not this task.
- **The ingestion API and freshness derivation** — tasks 10 and 09; this task consumes them.

## Acceptance criteria

- A `Bash` event classifies to `arbitrary-host-execution` regardless of its command string; no command
  content changes the classification.
- The requested structural safeguards are seeded, tagged STRUCTURAL, carry a cadence, and the registry
  resolves them as governing `(arbitrary-host-execution, repo=X)`.
- With every structural safeguard freshly attested, the Bash float sits at the min of their ceilings;
  with one **unattested or expired**, the float drops to that safeguard's caution floor.
- Impact caps hard: a catastrophic reachable-authority value ceilings the float low even when every
  other safeguard holds.

## Demo

The dashboard shows a **capability panel for Bash**: the worst-case sentence ("this tool can do
anything the host process can, which right now includes …"), the list of *requested* structural
safeguards, and the current float. Attest `ephemeral-environment` and the float rises; let it expire
and it falls back — delegation *bought*, then *lapsed*, on one screen.

## Notes

- Keep the capability model domain-agnostic in shape: "arbitrary host execution" is the software
  instance of "an action whose blast radius is its whole environment"; the type must not bake in shell
  specifics.
- Reuse the same `Selector` / `Safeguard` / registry types — no new dialect. Bash is data seeded into
  the existing engine, not a special case in the code.
