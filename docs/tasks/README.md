# Tasks

Ordered, self-contained units of work for building sailguarding. See [`../../SPEC.md`](../../SPEC.md)
for the model these tasks implement.

The first five form a walking skeleton: **observe → store → classify → score-contract**. The next
arc closes the core loop — **govern → measure → recommend → band** — turning the score contract into
a real recommendation over governed, measured safeguards.

| # | Task | Depends on | Status |
|---|------|------------|--------|
| 01 | [Scaffold and event schema](01-scaffold-and-event-schema.md) | — | done |
| 02 | [Storage strategy: branch sink](02-storage-strategy-branch-sink.md) | 01 | done |
| 03 | [Claude Code sensor](03-claude-code-sensor.md) | 01, 02 | done |
| 04 | [Selector classification engine](04-selector-classification-engine.md) | 01, 02 | done |
| 05 | [Scoring-function contract](05-scoring-function-contract.md) | 01, 04 | done |
| 06 | [Safeguards & bindings](06-safeguards-and-bindings.md) | 04, 05 | done |
| 07 | [Action tree & error budgets](07-action-tree-and-budgets.md) | 01, 04, 06 | todo |
| 08 | [Evidence ingestion & measurement](08-evidence-ingestion-and-measurement.md) | 02, 06 | todo |
| 09 | [Feature-vector assembly](09-feature-vector-assembly.md) | 05, 06, 07, 08 | todo |
| 10 | [Behaviour bands & hysteresis](10-behaviour-bands-and-hysteresis.md) | 05 | todo |

Each task lists its own scope, non-goals, and acceptance criteria. Keep tasks self-contained: a
reader should be able to act on one without reconstructing this conversation.

Per the definition of done in [`../../CLAUDE.md`](../../CLAUDE.md), a task is not complete until it is
**demonstrated** — so tasks 06+ carry a **Demo** section, and most extend the standing demo surface
(the web dashboard, `python -m sailguarding.web`) rather than a one-off script.
