# Tasks

Ordered, self-contained units of work for building sailguarding. See [`../../SPEC.md`](../../SPEC.md)
for the model these tasks implement.

The first five form a walking skeleton: **observe → store → classify → score-contract**. Evidence
ingestion, calibration, and behaviour-band enforcement come after and are not yet written up.

| # | Task | Depends on | Status |
|---|------|------------|--------|
| 01 | [Scaffold and event schema](01-scaffold-and-event-schema.md) | — | done |
| 02 | [Storage strategy: branch sink](02-storage-strategy-branch-sink.md) | 01 | done |
| 03 | [Claude Code sensor](03-claude-code-sensor.md) | 01, 02 | done |
| 04 | [Selector classification engine](04-selector-classification-engine.md) | 01, 02 | done |
| 05 | [Scoring-function contract](05-scoring-function-contract.md) | 01, 04 | done |

Each task lists its own scope, non-goals, and acceptance criteria. Keep tasks self-contained: a
reader should be able to act on one without reconstructing this conversation.
