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

# Build the React SPA so `sg serve` has something to serve. Guarded on npm: the Python engine and
# its tests do not need Node, so a machine without it can still sync and run checks.
if command -v npm >/dev/null 2>&1; then
  echo "==> Building front-end (frontend: npm ci && npm run build)"
  (cd frontend && npm ci && npm run build)
else
  echo "==> Skipping front-end build (npm not found); 'sg serve' will show a build-me page." >&2
fi

if [[ "${1:-}" == "check" ]]; then
  echo "==> Lint (ruff check)"
  uv run ruff check .
  echo "==> Format check (ruff format --check)"
  uv run ruff format --check .
  echo "==> Type-check (mypy)"
  uv run mypy
  echo "==> Tests (pytest)"
  uv run pytest
  if command -v npm >/dev/null 2>&1; then
    echo "==> Front-end type-check (frontend: npm run typecheck)"
    (cd frontend && npm run typecheck)
  fi
fi

echo "==> Done."
