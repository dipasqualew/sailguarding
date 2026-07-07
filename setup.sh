#!/usr/bin/env bash
# Idempotent developer bootstrap for the sailguarding engine.
# Brings a clean machine to a state where lint, type-check, and tests pass.
#
#   ./setup.sh          install/sync the dev environment
#   ./setup.sh check    also run lint + type-check + tests
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required but not installed. Install it from https://docs.astral.sh/uv/ and re-run." >&2
  exit 1
fi

echo "==> Syncing dependencies (uv sync --all-packages)"
# --all-packages so workspace members (the `cli` / `sg` package) and their deps are installed too,
# not just the root engine.
uv sync --all-packages

if [[ "${1:-}" == "check" ]]; then
  echo "==> Lint (ruff check)"
  uv run ruff check .
  echo "==> Format check (ruff format --check)"
  uv run ruff format --check .
  echo "==> Type-check (mypy)"
  uv run mypy
  echo "==> Tests (pytest)"
  uv run pytest
fi

echo "==> Done."
