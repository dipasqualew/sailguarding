# sailguarding — Product Spec

*Status: draft / exploration. This document is the shared model, not a commitment to an API.*

## What this is

sailguarding is tooling for a job that is about to exist: modelling the work a team hands to
agents, defining the safeguards that make that handover safe, measuring whether those safeguards
actually hold, and turning the result into a per-action recommendation for how much to delegate.

The bet is that "how much should an agent do here" is not a property of the model or of your
nerve. It is a property of **this action, in this context, given the safeguards that are currently
proven to work.** sailguarding is the system that records the work, holds the safeguards, measures
them over time, and computes the answer.

We start as a **system of record**: it observes what agents do, maps each action to the safeguards
that govern it, ingests evidence of whether those safeguards are holding, and reports a delegation
recommendation. It is deliberately built on hook points that can later *enforce* the recommendation,
so the control-plane version is an additive step, not a rewrite.

First use case is software engineering (a SaaS webapp codebase, Claude Code as the first harness),
but the model is domain-agnostic on purpose — the same structure describes buying a sofa or
approving a housing-regulation change.

## The core loop

```
observe → classify → govern → measure → recommend → (later) enforce
```

1. **Observe.** A harness adapter records what the agent did (tool events) with the context it ran in.
2. **Classify.** Each event is resolved to an **action** — the unit we actually reason about.
3. **Govern.** Each action is bound to the **safeguards** that must hold for it, and to an **error budget**.
4. **Measure.** Operating teams supply evidence; the platform scores each safeguard's effectiveness over time.
5. **Recommend.** Safeguard effectiveness + error budget → a delegation float in `[0,1]` → a team-defined behaviour band.
6. **Enforce (future).** The same hook that observed the action gates it according to the band.

Delegation is **earned**: an agent gets more autonomy on an action only while the safeguards
governing it are demonstrably holding, and loses it as they decay.

## Domain model

### Action (the recursive unit)

There is one self-similar type. Root or leaf, every node is a unit of work that can be decomposed
and that carries an envelope, safeguard bindings, an error budget, and a computed delegation float.

- What we loosely call a **goal** is just the root action ("ship a regulation-compliant update").
- What we loosely call a **task** is just a node we have not decomposed further ("write the tests").
- A delegation decision can be read at any level: hand off a whole subtree if the parent sits inside
  its envelope, or only specific leaves.

We do **not** model "goal" and "task" as separate concepts. One recursive `Action` type with children.

### Context (a dimension space, not a fixed schema)

Context is an **open set of typed dimensions** describing where an action runs. It is never
hardcoded, so the model generalises past software.

- Software: `{ team, repo, environment, service }`
- Sofa: `{ home, room, budget_holder }`

Everything that binds to context — safeguards, budgets, envelopes — binds via a **selector** (a
predicate over dimensions, with wildcards), not to a fixed entity:

- `team=*, repo=checkout` — all users, one repo
- `home=my-house, room=living`

This is label-selector semantics (cf. Kubernetes labels, OPA). It is the article's *Operational
Design Domain* made concrete: the region of context where a given envelope is valid.

### Envelope (the risk score)

For a given `(action, context)`, the envelope scores four axes:

- **Impact** — how much damage if it goes wrong, how widely spread.
- **Prevention** — can we stop the bad outcome by construction, or reduce its odds?
- **Detection** — will we find out it went wrong, and how fast?
- **Reversal** — can we undo it, and at what cost?

Impact and reversal are largely human-set and stable. Prevention and detection are **driven by live
safeguard effectiveness** — they improve as safeguards prove themselves and decay as safeguards rot.

### Safeguard (two tiers — the separation of powers)

This is the governance keystone. A safeguard has two authors:

- **Safeguarding team defines the *class* and the *scoring*.** They declare what must be true for an
  action to be delegable and how failing it scores — e.g. for code writing: tests have high
  coverage, low flakiness, run before merge, and don't grow too expensive over time; and "flakiness
  above threshold T costs S points." They set the bar. They do **not** specify how any metric is
  computed or ingested.
- **Operating team defines the *implementation*.** They build and wire the actual mechanism that
  computes and ingests the metric (how *this* repo measures flakiness, coverage, cost) in their
  context. They meet the bar and supply the evidence.

Delegation to agents is **earned** by the operating team fulfilling the controls the safeguarding
team set. This mirrors SR 11-7's independent validation: the standard-setter is separate from the
implementer.

Each safeguard is also tagged **structural vs. human-dependent** (a spending cap the model cannot
exceed vs. "I'll review the shortlist"). Human-dependent safeguards move the score less than they
appear to, and the platform should reflect that.

### The lifecycle — requested, attested, holding, expired

A safeguard is not a static fact; it has a **lifecycle**, and the platform holds every stage.

- **Requested.** The safeguarding team reads the traces — the observed tool events — and names a
  control an action needs: "Bash needs ephemeral environments." That is a *requested* safeguard.
  Requesting it does not make it true; it declares the bar and the cadence (below).
- **Attested.** The operating team meets the bar in *their* context and supplies **evidence** through
  an ingestion API: an attestation that the control holds for `repo=X`, carrying its **reasoning**
  (how they know) and a **validity window**. Evidence is not only a metric — for a structural control
  like "ephemeral environments" it is a claim plus its justification; for a health metric it is the
  value plus when it was measured. Either way it is time-stamped and time-boxed.
- **Holding.** While fresh evidence exists, the safeguard *holds* and lifts the delegation float as
  its scoring allows.
- **Expired.** The safeguarding team sets a **cadence** — how often the control must be re-evidenced
  (weekly, per-release, per-deploy). A fresh attestation **buys allowance for exactly one window**;
  when it lapses the safeguard stops holding and the float **decays toward the human**. This is design
  principle 1 ("autonomy decays when safeguards do") given a concrete clock: allowance is a
  subscription, not a one-time purchase.

The consequence is that **evidence has a shelf life**. Signal derivation is freshness-aware: a
measurement outside its window is *stale* and contributes no signal, so a safeguard with only stale
evidence fails toward caution exactly as an unmet one does. Sending this week's evidence for `repo=X`
buys `repo=X` a week of allowance; next week needs new data.

### Capability tools and the worst case

Tools split into two kinds, and they are governed differently.

- A **bounded tool** acts within a declared surface: `Edit` touches a path, `Read` returns bytes.
  Classification can recognise *what* it did, and a safeguard can bind to that.
- A **capability tool** executes with the host process's full authority: `Bash(X)` runs arbitrary
  code as whatever user, with whatever credentials and network reach, the harness holds. You cannot
  govern it by inspecting `X` — that is trying to out-parse an adversarial shell, and effects hide
  inside command substitution and pipes-into-interpreters.

So for a capability you **assume the worst**: it can do anything the host process can — the **union of
reachable authority** (credentials in the environment, network position, filesystem reach). That is
the impact you model, and it is knowable *without reading a single command*. A team that runs the
harness with production-write credentials in scope has a high-impact Bash whether or not any command
ever uses them.

This inverts the earned-delegation loop. For a bounded action, autonomy is *earned* by a track record
of holding safeguards. For a capability a track record is worthless — call *N+1* can do anything call
*N* could not — so autonomy is **bought by structural safeguards that shrink the reachable authority**:
ephemeral sandboxes, secrets brokering, egress allowlists, operation audit. These are the requested
safeguards; the operating team attests to them on the cadence. Good modelling here is not "what did
this command do." It is making the team read the sentence *"this tool can do anything the host process
can, which right now includes writing your production database,"* and showing which structural
safeguards take that clause out of the sentence.

### Measurement: health vs. efficacy

The platform is agnostic to any specific safeguard, but it forces one honest distinction per metric:

- **Health** — cheap, continuous, leading. Flakiness, coverage delta, CI latency, false-positive
  rate. Rising flakiness = a detection channel losing trust.
- **Efficacy** — expensive, lagging, the number that matters. `P(catches a bad change | change was
  actually bad)`, back-tested against outcomes (reverts, hotfixes, incidents). Computable at MVP
  from git + CI alone.

Selling health as if it were efficacy is the trap. The platform must let a safeguard declare which
it is measuring, and never conflate them.

### Error budget / risk appetite

Attached to an **action class × context selector**, set with the business, not per-mood. This is the
second number the score is read against. Budgets and safeguards inherit down the action tree;
inheritance/override semantics are defined once, up front.

### Delegation float and behaviour bands

The recommendation for an `(action, context)` is a float in `[0,1]` (0 = human does it, 1 = full
agent autonomy). **The framework does not compute this number.** How safeguards produce the float is
*modelling*, and it belongs to the safeguarding team — because only they know how risk behaves in
their domain.

**Scoring is a team-authored function, and it is the team's IP.** How the measured signals become a
float is not something the platform prescribes. Each safeguarding team writes a **scoring function** —
real code — for *their* organisation, and it is a competitive asset, not a config value. It takes the
measured signals for an `(action, context)` — a feature vector the platform assembles from every bound
safeguard, the context, and the remaining budget — and returns a float in `[0,1]`.

The function can be anything:

- **Compositional / interpretable** — each safeguard maps its metric to a ceiling (flakiness ≤ X →
  `0.9`, ≤ 2X → `0.5`, > 2X → `0`), and a composition combines them. `min` (the weakest safeguard
  binds) is the obvious first example, but the composition is itself just code — weighted, gated,
  whatever the risk model says.
- **Numerical** — a model `f(R^n) → [0,1]` over the whole feature vector.
- **Learned** — an ML or LLM classifier trained/prompted on the team's own outcome history.

Whatever the architecture, two properties should hold, and it is the team's job to guarantee them:

- **Impact caps hard.** A catastrophic action cannot score high because detection is good and the
  budget is fat. In the compositional pattern this is automatic — impact is the safeguard that
  ceilings low. In a monolithic model the team must build it in. Either way it avoids the FMEA-RPN
  trap of a mean that hides catastrophic-but-rare failures.
- **Remaining budget pulls the float down**, collapsing it toward the human as the budget is spent.

**A clean division of labour, borrowed from MLOps:**

- **The platform owns the feature substrate** — it collects, calibrates, versions, and serves the
  measured signals over time (a feature store), and *executes* the team's function against them.
- **The team owns the model** — the scoring function itself, as IP.

Because the function and the signals are IP, **execution runs in the team's own environment**, never
the vendor's. That is not a nicety — it is why the engine is open source and self-hosted, and why the
enterprise product sells governance *around* the function rather than the function.

**Two honest constraints on "any function":**

- **The scorer is itself a model, so it inherits model risk management.** Every decision must log its
  inputs, the function version, and the output, so "why was this delegated at `0.9`?" is answerable in
  an audit months later (SR 11-7 again). Arbitrary code is fine; unversioned, unlogged arbitrary code
  is not.
- **Beware the reflexive trap.** Using an opaque LLM to decide how much to trust an opaque LLM just
  relocates the trust problem — you now have a second model to safeguard. The platform stays neutral on
  architecture, but its examples lean interpretable, and a team reaching for a black-box scorer should
  know it has imported another model to validate.

**A scoring function is a hypothesis until data confirms it.** "flakiness X is safe up to `0.9`" is a
guess when a team authors it. Calibration is where the platform earns its keep: it collects outcomes
and shows whether actions delegated at `0.9`-with-flakiness-`X` *actually* failed more, so teams
**move the number against evidence, not intuition.** Measurement is not reporting; it is calibration of
the scoring function.

**What the platform provides (and what it doesn't).** Not the risk model. Only: the **feature
substrate** (calibrated signals over time); the **execution surface** for team functions; a **library
of ready-made functions and patterns** (ceilings, `min`-composition, common shapes) as starting points;
and the **calibration data loop** that turns a hypothesised function into a justified one.

**Behaviour bands.** The safeguarding team maps the resulting float to enforced human+agent
behaviour. Example for test writing:

- `0` — "I write the tests myself."
- `0 < x < 0.5` — "I author the use cases; the agent writes the implementation."
- `0.5 < x < 1` — "I review the tests the agent wrote."
- `1` — "I don't look."

Two requirements on the banding:

- **Monotonic + partitioned.** Higher float always = more autonomy; bands cover `[0,1]` with no gaps
  or overlaps.
- **Hysteresis at boundaries.** The float wobbles run-to-run (flakiness *is* noise). Require it to
  cross a band boundary by a margin before the enforced behaviour changes, so behaviour doesn't flap
  when the score hovers on a line.

## Action classification is part of the safeguard

Resolving a raw tool event to an action is not plumbing — it is **part of the risk calculus**. A
path-glob classifier calls `Edit(foo.test.ts)` "test writing," but misses
`Bash(echo "print('hello')" > hello.py)`, which writes code through a shell. The *quality* of
classification bounds the quality of every safeguard downstream: you cannot govern an action you
failed to recognise.

So classification is a **pluggable strategy**, and its quality is a modelling choice the team makes:

- **Heuristic / deterministic** (globs over paths, command patterns, context labels) — cheap, fast,
  the default we ship first. Low quality, and honest about it.
- **Classic ML classifier** — better, more setup.
- **Small model / LLM classifier** — highest quality, most expensive.

For MVP: ship the heuristic strategy, capture in the schema that it is replaceable, and let teams
declare their classification strategy per action class or context. Where classification is
probabilistic, it should fail toward caution (toward a lower float).

**Selector-driven classification.** An action is defined by a **selector over
`(tool-event attributes × context)`** — e.g. "edits matching `**/*.test.ts` in repo `checkout`" *is*
the test-writing action. Safeguards attach to that selector. Events matching no selector become a
triage queue a human models. The action tree and the selectors co-define each other; for the
heuristic strategy, "classification" is just matching — no model required.

**Bounded tools, not capabilities.** This bounds governance for *bounded* tools, where recognising
the action is the whole game. A **capability tool** — `Bash`, which executes arbitrary code at the
host process's authority — is the exception (see *Capability tools and the worst case* above): you do
not try to predict what `Bash(X)` will do. Classification only recognises that it *is* arbitrary host
execution; governance then moves to structural safeguards and the freshness contract, not to parsing
the command.

## Architecture

### Harness adapters

The first adapter is a **Claude Code plugin with a pre-tool-use hook**. The hook is a **sensor**
now (record the tool event + context) and the **actuator** later (gate the event per the band). Same
hook point, so enforcement is additive.

- Pre-tool-use has **no outcome** — it captures *what the agent did*, not whether it worked.
  Outcome/evidence (CI results, reverts) arrives through a separate ingestion and is *joined* to the
  action stream later. Keep the two streams distinct.

### Storage strategy (pluggable; branch is the default)

Storage is a strategy, not a fixed backend. The first implementation writes to a **branch of the
repo** — zero infra, versioned, git-native audit trail, works offline, open-source-friendly.

Two things the branch default must respect:

- **Separate the event log from the metrics.** Git is a fine append-only log and a terrible
  time-series database. The branch holds the raw event log; **derived safeguard metrics** live behind
  a separate (pluggable) metrics sink that can target a real store later.
- **Shard to avoid merges.** Many sessions appending to one file = merge conflicts. One append-only
  file per session/day (JSONL); nothing shared, nothing to merge; aggregate afterward.

### Evidence ingestion

Operating teams wire metric sources (CI, test runners, git history for reverts/hotfixes, later
incident tooling). The platform scores each safeguard's health and efficacy from this evidence
against the thresholds/trends the safeguarding team declared.

Ingestion is an **API**, not only a scraper. The operating team **posts attestations** — a safeguard
id, the context, the attested value or claim, the **reasoning**, and a **validity window** derived
from the safeguarding team's cadence. The platform time-boxes each attestation; expired evidence is
dropped from signal derivation, so allowance lapses unless it is renewed on the cadence. Automated
metric sources (CI, git history) are one kind of attestation the operating team wires up; a human
posting "ephemeral envs verified for `repo=X`, valid one week" is another — the same shape, the same
shelf life.

## Implementation order

1. **Extraction from Claude Code.** A plugin + pre-tool-use hook that records tool events and
   context to a storage strategy (branch default, JSONL sharded per session). Build for code first;
   keep the schema domain-agnostic.
2. **Define action trees + safeguards + budgets.** Seed the tree bottom-up from observed events
   (curate, don't author from a blank page). Safeguards carry class + scoring (safeguarding team) and
   bind to context selectors; operating teams wire the mechanisms. Fix budget inheritance semantics.
3. **Ingest safeguard performance and attach to `(action, context)`.** e.g. "no flaky unit tests" is
   a code-writing safeguard bound to `team=*, repo=checkout`. Effectiveness feeds the
   prevention/detection axes; with the budget it produces the current delegation float. This closes
   the loop.

## Open core

- **Open source:** action modelling, single-team measurement, local dashboards, the delegation
  recommendation, the Claude Code adapter, heuristic classification, branch storage. Enough to make
  a delegation engineer productive and to grow a community around the schema.
- **Enterprise:** multi-team/org rollup, RBAC, **independent-validation workflow** (validator ≠
  author), audit export with SR 11-7 / EU AI Act mappings, historical retention, higher-quality
  classification strategies, non-branch storage backends.

## Design principles (non-negotiable)

1. **Delegation is earned, never asserted.** Autonomy tracks proven safeguards; it decays when they do.
2. **Measure honestly.** Health is not efficacy. Never sell one as the other.
3. **Structural beats human-dependent.** Prefer safeguards enforced by construction; score the
   difference.
4. **Fail toward caution; impact caps hard.** However a team models scoring, the float must fail
   toward the human — unproven signals keep it low, and catastrophic impact caps it regardless of any
   other signal.
5. **Enforcement-ready from day one.** Everything is machine-readable and hangs off a hook that can
   later gate. The system of record is the first half of a control plane, not a dead end.
6. **The platform is substrate; the risk model is the team's IP.** It hosts classification, storage,
   and the feature substrate as pluggable strategies and *executes* the team's scoring functions in
   the team's own environment. The platform never owns — or sees — the risk model.
7. **Every decision is auditable.** Inputs, function version, and output are logged for each score, so
   any delegation is explainable long after the fact.

## Open questions

1. **Scoring-function contract** — the exact shape of the feature vector in, the `[0,1]` out, and how
   a team declares, versions, and registers the function. This is the platform's central API; pin it
   down first.
2. **Execution model for costly scorers** — an ML/LLM scoring function is slow, non-deterministic, and
   costs money; it cannot run synchronously on every pre-tool-use hook. Needs caching, versioning, a
   latency budget, and a fallback when the scorer is unavailable (fail toward caution).
3. **Selector language scope** — is per-event matching (paths + commands + context labels) enough for
   v1, or must selectors express *sequences* ("edited billing, then deployed")?
4. **Budget inheritance** — does a leaf's budget override its parent's, or compose with it?
5. **Cross-context rollup** — how safeguard effectiveness aggregates across many repos/contexts for an
   org-level view without losing the per-context truth that makes the envelope meaningful.
6. **Freshness & cadence semantics** — how a safeguarding team declares a cadence, how a validity
   window attaches to an attestation, and the decay shape between fresh and expired (a cliff at
   expiry, or a ramp as the window runs down).
