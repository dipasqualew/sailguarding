# 06 — Safeguards & bindings

**Status:** todo
**Depends on:** 04, 05

## Context

This is the governance keystone — the SPEC's *separation of powers* made into types. A safeguard has
two authors: the **safeguarding team** defines the *class* (what must be true for an action to be
delegable) and the *scoring* (how failing it scores); the **operating team** defines the
*implementation* (how this context actually measures it). Task 05 built the scoring seam and a
`SafeguardSignal(id, metric, value)`; task 08 will build the measurement. This task builds the thing
in between: the **governed safeguard** and how it **binds to context**.

Two properties of a safeguard the platform must carry honestly, because they change how much a
signal is allowed to move the float:

- **Structural vs. human-dependent** — a spending cap the model cannot exceed vs. "I'll review the
  shortlist". Human-dependent safeguards move the score less than they appear to.
- **Health vs. efficacy** — which one a given metric is measuring. Health is cheap, leading, and a
  proxy; efficacy is the lagging number that matters. The platform must let a safeguard *declare*
  which, and never conflate them.

A safeguard binds to context through a **selector** (task 04) — the same predicate language
classification uses, which is exactly why task 04 put both event and context attributes in one
`Selector`. "No flaky tests, `team=*, repo=checkout`" is a safeguard bound to a region of context.

## Scope

- **`Safeguard` type:** id, human label, the metric it scores against, its **structural /
  human-dependent** tag, and its **health / efficacy** declaration. Versioned and serializable.
- **`SafeguardBinding`:** a `Safeguard` bound to a `Selector`, so "which safeguards govern this
  `(action, context)`?" is answerable. Serializable alongside the selector rules.
- **Binding registry:** resolve the set of safeguards that apply to a given `(action, context)` by
  evaluating the bound selectors — the input list that task 09 will assemble a feature vector from.
- **Injection:** the registry is a pluggable seam with an in-memory default; stub safeguards are
  usable in tests with no real risk model.

## Out of scope

- **Live measurement** (task 08) — a safeguard declares *what* it measures and *which kind*; ingesting
  the evidence and computing the signal comes later.
- **The action tree and error budgets** (task 07).
- **Scoring composition** (task 05, done) — the ceiling functions live in the team's scoring
  function; this task supplies the governed inputs it consumes, not the composition.

## Acceptance criteria

- A `Safeguard` is versioned, serializable, and round-trip tested, carrying its structural/
  human-dependent tag and its health/efficacy declaration.
- A `SafeguardBinding` binds a safeguard to a selector and round-trips.
- The registry resolves exactly the safeguards whose selectors match a given `(action, context)`,
  and the tie/overlap behaviour is documented (mirroring the classifier's specificity handling where
  it applies).
- The registry is injected; a stub set of bindings drives tests without any real risk model.

## Demo

A **Safeguards panel** on the dashboard for the demo action: each governing safeguard listed with its
structural/human-dependent tag and health/efficacy label, and the selector it bound through. Toggling
a binding on/off adds or removes its ceiling from the score, so the effect on the delegation float is
visible — proving the registry actually decides which safeguards reach the scorer.

## Notes

- Reuse `Selector` from task 04 verbatim; do not fork a second predicate language. If selector
  *sequences* are ever needed (open question #3), that is a change to the shared selector, not to
  safeguards.
- Keep the type domain-agnostic: a safeguard governs a sofa purchase as readily as a code edit.
