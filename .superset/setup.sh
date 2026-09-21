#!/usr/bin/env bash
# Superset workspace setup. Idempotent; safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="${SUPERSET_ROOT_PATH:?SUPERSET_ROOT_PATH is not set}"
mkdir -p .superset/.generated

# Untracked files from the main checkout (never committed).
if [ ! -f .env ]; then
  if [ -f "$ROOT/.env" ]; then
    # No chmod 600: the api container runs as uid 1001 and reads the bind-mounted .env itself.
    cp "$ROOT/.env" .env
  else
    echo "warn: $ROOT/.env not found, falling back to .env.example placeholders" >&2
    cp .env.example .env
  fi
fi

# Local venv for pytest / ruff / mypy (3.12 = Dockerfile + pyproject target).
# Explicit install: uv may have python-downloads=manual, and this is a no-op once installed.
uv python install 3.12
uv venv --python 3.12 --allow-existing .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt

# This workspace's free host ports + compose project name.
python3 .superset/ports.py allocate "$PWD" > .superset/.generated/ports.env
