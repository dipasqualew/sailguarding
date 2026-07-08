# Tasks

Ordered, self-contained units of work for building sailguarding. See [`../../SPEC.md`](../../SPEC.md)
for the model these tasks implement.

The first five form a walking skeleton: **observe → store → classify → score-contract**. Tasks 06–08
close the core loop — **govern → measure → recommend** — over governed, measured safeguards. Tasks
09–12 are the **attestation reframing**: a safeguard is *requested* by the safeguarding team from the
traces and *attested* by the operating team on a **cadence**, evidence has a shelf life, and `Bash` is
modelled as a **capability tool** — assume the worst, buy delegation with structural safeguards rather
than earn it with a track record. See the SPEC's *lifecycle* and *capability tools* sections.

| # | Task | Depends on | Status |
|---|------|------------|--------|
| 01 | [Scaffold and event schema](01-scaffold-and-event-schema.md) | — | done |
| 02 | [Storage strategy: branch sink](02-storage-strategy-branch-sink.md) | 01 | done |
| 03 | [Claude Code sensor](03-claude-code-sensor.md) | 01, 02 | done |
| 04 | [Selector classification engine](04-selector-classification-engine.md) | 01, 02 | done |
| 05 | [Scoring-function contract](05-scoring-function-contract.md) | 01, 04 | done |
| 06 | [Safeguards & bindings](06-safeguards-and-bindings.md) | 04, 05 | done |
| 07 | [Action tree & error budgets](07-action-tree-and-budgets.md) | 01, 04, 06 | done |
| 08 | [Evidence ingestion & measurement](08-evidence-ingestion-and-measurement.md) | 02, 06 | done |
| 09 | [Attestation & the freshness contract](09-attestation-and-the-freshness-contract.md) | 06, 08 | done |
| 10 | [The evidence ingestion API](10-evidence-ingestion-api.md) | 09 | todo |
| 11 | [Capability tools & requested safeguards](11-capability-tools-and-requested-safeguards.md) | 04, 06, 07, 09 | todo |
| 12 | [Dashboard: requested → attested → holding → expired](12-dashboard-requested-attested-holding-expired.md) | 09, 10, 11 | todo |

Each task lists its own scope, non-goals, and acceptance criteria. Keep tasks self-contained: a
reader should be able to act on one without reconstructing this conversation.

**Deferred.** *Feature-vector assembly* and *behaviour bands & hysteresis* (former tasks 09–10) are
parked until the reframing lands — the freshness-aware signal changes what the vector carries, and
bands sit on top of a float the attestation model reshapes. They return as follow-ups after task 12.

Per the definition of done in [`../../CLAUDE.md`](../../CLAUDE.md), a task is not complete until it is
**demonstrated** — so tasks 06+ carry a **Demo** section, and most extend the standing demo surface
(the web dashboard, `sg serve`) rather than a one-off script.
