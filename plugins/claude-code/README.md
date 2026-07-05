# sailguarding — Claude Code sensor plugin

The first sailguarding harness adapter: a **pre-tool-use hook** that records what the agent is
about to do. It is a **sensor now** and the **actuator later** — the same hook point will gate
actions against a behaviour band once enforcement lands, so that step is additive, not a rewrite.

## What it does

On every tool call, before the tool runs, Claude Code fires the hook with the PreToolUse payload
(tool name, tool input, session id, cwd). The hook pipes that payload to the sailguarding engine,
which builds one append-only [`EventRecord`](../../src/sailguarding/domain/event.py) carrying:

- the raw tool name and (redacted) tool input,
- the resolved context — repo and git branch, plus team/environment where configured,
- the **work-unit correlation key** (git branch + HEAD commit) so later tasks can attribute the
  event to the commit-sized unit of work it lands in,
- session id, timestamp, harness id (`claude-code`), and schema version,

and writes it through the configured storage strategy (the branch sink by default).

The hook is **fail-open**: if the engine errors or is slow, the tool call still proceeds. A
sensor must never break the agent session.

## Install

The plugin installs through the in-repo **local marketplace** (`.claude-plugin/marketplace.json`
at the repo root) via Claude Code's plugin flow — not by hand-editing settings. Nothing is
published; it installs straight from this repo.

```bash
# from the repo root
./scripts/plugin.sh install     # register the local marketplace, install + enable the plugin
./scripts/plugin.sh disable     # disable, uninstall, and remove the marketplace (no residue)
./scripts/plugin.sh status      # show marketplace + plugin state
```

The hook invokes the engine as `sailguarding record` (the console script installed with the
`sailguarding` package). If the engine isn't on `PATH` as a script, set `SAILGUARDING_ENGINE`
(e.g. `SAILGUARDING_ENGINE="python -m sailguarding.sensor"`).

## Configuration (environment variables)

| Variable                   | Purpose                                              | Default               |
| -------------------------- | ---------------------------------------------------- | --------------------- |
| `SAILGUARDING_BRANCH`      | Events branch the log is committed to                | `sailguarding/events` |
| `SAILGUARDING_TEAM`        | Ambient `team` context dimension                     | (unset)               |
| `SAILGUARDING_ENVIRONMENT` | Ambient `environment` context dimension              | (unset)               |
| `SAILGUARDING_REDACT_KEYS` | Extra comma-separated secret key patterns to redact  | (built-in set)        |
| `SAILGUARDING_ENGINE`      | Engine command the hook invokes                      | `sailguarding`        |
| `SAILGUARDING_TIMEOUT`     | Seconds to time-box the engine before giving up      | `5`                   |

## Contract

The hook contract (the JSON fields Claude Code writes to the hook's stdin) is pinned in
[`sailguarding/sensor/payload.py`](../../src/sailguarding/sensor/payload.py) and exercised by the
deterministic Claude Code mock in
[`sailguarding/sensor/mock.py`](../../src/sailguarding/sensor/mock.py), so the plugin and the
mock cannot silently drift from the real harness.
