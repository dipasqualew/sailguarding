#!/usr/bin/env bash
# sailguarding pre-tool-use sensor hook (thin).
#
# Claude Code fires this BEFORE a tool runs and writes the PreToolUse payload (session id,
# tool name, tool input, cwd, ...) to our stdin. We do the least possible here — pipe that
# payload straight to the engine's `record` entrypoint — and keep all real logic in the engine.
#
# As a SENSOR this hook is strictly fail-open: recording must never break the user's agent
# session. Whatever happens in the engine — an error, a missing binary, a slow write — the tool
# call must still proceed. So we time-box the engine, swallow every failure, emit nothing on
# stdout, and exit 0. Claude Code reads "exit 0 + no stdout" as "no decision, proceed normally".
# (Enforcement — the actuator role of this same hook — will change this posture deliberately.)
set -u

# The engine command. Defaults to the `sailguarding` console script on PATH; override with
# SAILGUARDING_ENGINE (e.g. "python -m sailguarding.sensor") when it isn't installed as a
# script. Left unquoted below on purpose so a multi-word command word-splits into argv.
engine="${SAILGUARDING_ENGINE:-sailguarding}"

# Time-box the engine so a slow write can never stall the agent. `timeout` isn't guaranteed to
# exist everywhere (it's `gtimeout` on some systems), so fall back to running the engine directly.
timeout_bin="$(command -v timeout || command -v gtimeout || true)"
limit="${SAILGUARDING_TIMEOUT:-5}"

if [ -n "$timeout_bin" ]; then
  "$timeout_bin" "$limit" $engine record >/dev/null 2>&1 || true
else
  $engine record >/dev/null 2>&1 || true
fi

exit 0
