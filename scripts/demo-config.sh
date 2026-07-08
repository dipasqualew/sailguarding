#!/usr/bin/env bash
# Demo: `sg config` chooses which data store the sensor commits to.
#
# This drives the REAL plugin hook (record → flush) against a throwaway git repo, twice:
#   1. with no config          -> the sensor commits to the git BRANCH (the default), and
#   2. after `sg config store filesystem --path ...` -> the sensor commits to a FILESYSTEM
#      directory instead, leaving the git branch untouched.
#
# It documents, executably, the acceptance for "extend `sg` to config which data store is used".
# Idempotent: it works in fresh temp dirs and cleans up after itself.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK="$REPO_ROOT/plugins/claude-code/bin/hook.sh"
# Run the engine straight from the venv so it needs nothing on PATH.
ENGINE="$REPO_ROOT/.venv/bin/python -m sailguarding.sensor"
SG="$REPO_ROOT/.venv/bin/sg"

WORK="$(mktemp -d)"
STORE="$(mktemp -d)"
REPO="$WORK/repo"
# Pin the operator config into the temp dir for BOTH `sg` and the sensor, so the demo never
# touches the developer's real ~/.config.
export SAILGUARDING_CONFIG="$WORK/sg-config.json"
CFG="$SAILGUARDING_CONFIG"
trap 'rm -rf "$WORK" "$STORE"' EXIT

git init -q -b trunk "$REPO"
git -C "$REPO" config user.name demo
git -C "$REPO" config user.email demo@localhost
git -C "$REPO" commit -q --allow-empty -m initial

# Fire one PreToolUse (record) then one Stop (flush) through the real hook, as Claude Code would.
turn () { # $1=tool
  local rec='{"session_id":"demo","cwd":"'"$REPO"'","hook_event_name":"PreToolUse","tool_name":"'"$1"'","tool_input":{"file_path":"a.py"}}'
  local stop='{"session_id":"demo","cwd":"'"$REPO"'","hook_event_name":"Stop"}'
  printf '%s' "$rec"  | env CLAUDE_PROJECT_DIR="$REPO" SAILGUARDING_CONFIG="$CFG" SAILGUARDING_ENGINE="$ENGINE" "$HOOK" record
  printf '%s' "$stop" | env CLAUDE_PROJECT_DIR="$REPO" SAILGUARDING_CONFIG="$CFG" SAILGUARDING_ENGINE="$ENGINE" "$HOOK" flush
}

echo "==> 1. No config: sensor commits to the git BRANCH (the default)"
"$SG" config show
turn Edit
echo "   sailguarding/events branch commits:"
git -C "$REPO" log --oneline sailguarding/events 2>/dev/null | sed 's/^/     /'
echo "   filesystem store ($STORE) is empty:"
find "$STORE" -type f | sed 's/^/     /' || true

echo
echo "==> 2. Reconfigure the data store with sg"
"$SG" config store filesystem --path "$STORE"
"$SG" config show

echo
echo "==> 3. Same hook, new store: sensor now commits to the FILESYSTEM directory"
turn Bash
echo "   filesystem store now holds the event log:"
find "$STORE" -type f | sed 's/^/     /'
echo "   captured events:"
cat "$STORE"/demo/*.jsonl | sed 's/^/     /'
echo "   git branch was NOT advanced by this turn (still one commit):"
git -C "$REPO" log --oneline sailguarding/events 2>/dev/null | sed 's/^/     /'

echo
echo "Done: the same sensor plugin, two data stores, selected entirely via \`sg config\`."
