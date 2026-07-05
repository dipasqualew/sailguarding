# 04 — Selector classification engine

**Status:** done
**Depends on:** 01, 02

## Context

A raw tool event (`Edit(foo.test.ts)`, `Bash(npm test)`) is not an **action**. "Writing tests",
"editing the billing path" are actions. Bridging that gap is classification — and per the SPEC it is
**part of the safeguarding calculus, not plumbing**: you cannot guard an action you failed to
recognise. A cheap rule that reads `Bash(echo "print('hi')" > hello.py)` as harmless text has punched
a hole in every envelope behind it.

So classification is a **pluggable strategy**, and this task ships the cheap, honest first one: a
**deterministic selector engine**. Higher-quality strategies (ML, small model, LLM) come later behind
the same interface; capture that seam now.

An **action is defined by a selector over `(tool-event attributes × context)`**. Safeguards will
attach to those selectors (task 05+). Events matching no selector are not silently dropped — they go
to a **triage queue** a human uses to model new actions bottom-up.

## Scope

- **Selector language (v1):** predicates over event attributes (tool name, file-path globs, command
  patterns) AND context dimensions (label match with wildcards, e.g. `repo=checkout`, `team=*`). Both
  sides must be expressible in one selector. Keep it declarative and serializable.
- **`ClassificationStrategy` interface:** `event → action_id | unmatched`. The selector engine is the
  first implementation; the interface must admit a future model-based strategy without change.
- **Matcher:** resolves each `EventRecord` to an action by evaluating registered selectors; fills
  `action_id`. Define and document conflict behaviour when multiple selectors match (e.g. most-specific
  wins, or explicit priority) — do not leave it implicit.
- **Triage queue:** unmatched events are collected and queryable, so a human can inspect them and
  author a new action + selector. This is the bottom-up modelling loop.
- **Fail toward caution:** ambiguous/unresolvable classification must bias toward the more conservative
  action (the one that will later yield a lower delegation float), never the more permissive one.

## Out of scope

- Model-based classifiers (later; same interface).
- Safeguards / scoring / the feature vector (task 05).
- Selector *sequences* ("edited billing, then deployed") — open question; v1 is per-event matching.

## Acceptance criteria

- Selector language matches on tool attributes and context labels together, wildcards included.
- `**/*.test.ts` edits in `repo=checkout` resolve to a "write tests" action; the same edit elsewhere
  does not.
- An event matching no selector lands in the triage queue and is retrievable.
- Multiple-match conflict resolves by the documented rule, covered by a test.
- Strategy is injected, not hard-wired; a stub strategy can replace the selector engine in tests.

## Notes

- The known weakness (a shell command writing code slips a path-glob selector) is expected and
  acceptable for v1 — it is the honest floor. Record it so the later ML/LLM strategy has a target to
  beat, and so classification quality is tracked as a first-class safeguard concern.

## Implementation

Shipped in `src/sailguarding/classification/`:

- `strategy.py` — the `ClassificationStrategy` seam (`event → Classification`, one of
  `MATCHED`/`UNMATCHED`/`AMBIGUOUS`). A stub returning a fixed `Classification` is a valid strategy,
  which is what lets tests swap the engine out.
- `selector.py` — the declarative, serialisable `Selector` (tool/path/command attributes **and**
  context labels in one object) and `SelectorRule` (selector → action + priority). Paths use
  `**`-aware globbing; tool names, commands, and context values use flat case-sensitive `fnmatch`.
- `engine.py` — `SelectorClassificationStrategy`, the first strategy over a rule registry.
- `matcher.py` — `Matcher`: runs a strategy, fills `action_id` on a resolved event, routes the rest
  to triage. Strategy injected, never hard-wired.
- `triage.py` — `TriageQueue`, the in-memory collector unmatched/ambiguous events land in.

**Conflict rule** (documented in `engine.py`, tested in `tests/classification/test_engine.py`):
most-specific selector wins → ties break by explicit `priority` → a residual tie across *different*
actions is `AMBIGUOUS`, which the matcher routes to triage rather than guessing. That refusal-to-guess
is "fail toward caution" made concrete before any delegation float exists — the conservative outcome
is a human modelling the action, never an arbitrary permissive pick.

**Known v1 weakness** recorded in `selector.py`'s module docstring and pinned by
`test_path_selector_misses_event_without_a_path`: a `Bash(echo ... > hello.py)` is matched as a
*command*, not a path edit, so a path-glob selector slips it — the honest floor a later model
strategy has to beat.
