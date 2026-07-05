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

# The engine command. Defaults to the `sailguarding` console script on PATH; override with
# SAILGUARDING_ENGINE (e.g. "python -m sailguarding.sensor") when it isn't installed as a
# script. Left unquoted below on purpose so a multi-word command word-splits into argv.
engine="${SAILGUARDING_ENGINE:-sailguarding}"

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
