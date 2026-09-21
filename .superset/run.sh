#!/usr/bin/env bash
# Superset "Run": start deps, migrate this workspace's fresh DB, then serve the API.
set -euo pipefail
cd "$(dirname "$0")/.."
. .superset/lib.sh
[ -n "${API_PORT:-}" ] || { echo "no ports allocated; run .superset/setup.sh first" >&2; exit 1; }

compose up -d --build --wait postgres redis
compose run --rm api alembic upgrade head
echo "API -> http://localhost:${API_PORT}  (postgres :${POSTGRES_PORT}, redis :${REDIS_PORT})"
exec docker compose -f docker-compose.yml -f .superset/compose.override.yml up --build api
