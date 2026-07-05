#!/usr/bin/env bash
# Idempotent install / disable of the sailguarding Claude Code sensor plugin.
#
# Installs through the in-repo LOCAL marketplace (.claude-plugin/marketplace.json) via Claude
# Code's own plugin flow — not by hand-editing settings. The marketplace is local to this repo:
# nothing is published or hosted, so it stays offline-friendly like the rest of the design.
#
#   ./scripts/plugin.sh install    register the local marketplace, install + enable the plugin
#   ./scripts/plugin.sh enable     enable the plugin (assumes it's installed)
#   ./scripts/plugin.sh disable    disable the plugin, uninstall it, remove the marketplace —
#                                  leaving no residue
#   ./scripts/plugin.sh status     show marketplace + plugin state
#
# Every action is idempotent: re-running `install` when already installed, or `disable` when
# already gone, is a no-op that still exits 0.
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

MARKETPLACE_NAME="sailguarding-local"
PLUGIN_NAME="sailguarding"
PLUGIN_REF="${PLUGIN_NAME}@${MARKETPLACE_NAME}"

if ! command -v claude >/dev/null 2>&1; then
  echo "error: the 'claude' CLI is required but was not found on PATH." >&2
  echo "       Install Claude Code, then re-run this script." >&2
  exit 1
fi

# Add the marketplace if it isn't registered yet; refresh it if it is. Either way we end with
# an up-to-date local marketplace, and re-running is safe.
ensure_marketplace() {
  if claude plugin marketplace list 2>/dev/null | grep -q "$MARKETPLACE_NAME"; then
    claude plugin marketplace update "$MARKETPLACE_NAME"
  else
    claude plugin marketplace add "$REPO_ROOT"
  fi
}

case "${1:-install}" in
  install)
    ensure_marketplace
    # `install` is idempotent in Claude Code; enable afterwards so a previously-disabled
    # plugin comes back on. Both tolerate the already-in-that-state case.
    claude plugin install "$PLUGIN_REF" --scope user
    claude plugin enable "$PLUGIN_REF" || true
    echo "==> Installed and enabled ${PLUGIN_REF}."
    ;;

  enable)
    claude plugin enable "$PLUGIN_REF"
    echo "==> Enabled ${PLUGIN_REF}."
    ;;

  disable)
    # Leave no residue: disable, uninstall, then drop the local marketplace. Each step is
    # guarded so a partially-installed or already-clean state still ends at exit 0.
    claude plugin disable "$PLUGIN_REF" 2>/dev/null || true
    claude plugin uninstall "$PLUGIN_REF" 2>/dev/null || true
    if claude plugin marketplace list 2>/dev/null | grep -q "$MARKETPLACE_NAME"; then
      claude plugin marketplace remove "$MARKETPLACE_NAME" 2>/dev/null || true
    fi
    echo "==> Disabled and removed ${PLUGIN_REF}; no residue left."
    ;;

  status)
    echo "== Marketplaces =="
    claude plugin marketplace list || true
    echo
    echo "== Plugins =="
    claude plugin list || true
    ;;

  *)
    echo "usage: $0 {install|enable|disable|status}" >&2
    exit 2
    ;;
esac
