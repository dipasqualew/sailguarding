#!/usr/bin/env bash
# sailguarding sensor hook (thin), shared by every hook role.
#
#   hook.sh record   PreToolUse         -> stage the tool call in the local spool (no git)
#   hook.sh flush     Stop / SessionEnd -> commit the session's staged events to the branch
#
# Claude Code writes the hook payload (session id, tool name/input, cwd, ...) to our stdin. We do
# the least possible here — pipe that payload to the engine's subcommand — and keep all real
# logic in the engine.
#
# As a SENSOR this hook is strictly fail-open: neither recording nor flushing may break the
# user's agent session. Whatever happens in the engine — an error, a missing binary, a slow
# write — the tool call (or session lifecycle) must still proceed. So we time-box the engine,
# swallow every failure, emit nothing on stdout, and exit 0. Claude Code reads "exit 0 + no
# stdout" as "no decision, proceed normally". (Enforcement will change this posture deliberately.)
set -u

subcommand="${1:?usage: hook.sh <record|flush>}"

# The engine command. `sg` is the one command the operator installs on PATH, and it carries the
# sensor's `record`/`flush` subcommands — so that is what we shell into. Override with
# SAILGUARDING_ENGINE (e.g. "python -m sailguarding.sensor") when `sg` isn't installed as a script
# (tests do this). Left unquoted below on purpose so a multi-word command word-splits into argv.
#
# Claude Code launches hooks with a GUI/login PATH that may not include the user's bin dir, so we
# resolve `sg` to an absolute path — trying PATH first, then the conventional ~/.local/bin — rather
# than trusting it to be found. No engine resolvable is itself fail-open: do nothing, exit 0.
engine="${SAILGUARDING_ENGINE:-}"
if [ -z "$engine" ]; then
  engine="$(command -v sg 2>/dev/null || true)"
  if [ -z "$engine" ] && [ -x "$HOME/.local/bin/sg" ]; then
    engine="$HOME/.local/bin/sg"
  fi
fi
[ -z "$engine" ] && exit 0

# Time-box the engine so a slow write can never stall the agent. `timeout` isn't guaranteed to
# exist everywhere (it's `gtimeout` on some systems), so fall back to running the engine directly.
timeout_bin="$(command -v timeout || command -v gtimeout || true)"
limit="${SAILGUARDING_TIMEOUT:-5}"

if [ -n "$timeout_bin" ]; then
  "$timeout_bin" "$limit" $engine "$subcommand" >/dev/null 2>&1 || true
else
  $engine "$subcommand" >/dev/null 2>&1 || true
fi

exit 0
