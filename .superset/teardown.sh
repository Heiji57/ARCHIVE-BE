#!/usr/bin/env bash
# Superset workspace teardown. Best-effort: never block workspace deletion.
set -uo pipefail
cd "$(dirname "$0")/.."
. .superset/lib.sh

# Stop the stack and delete this workspace's DB/redis volumes and built image.
if [ -n "${COMPOSE_PROJECT_NAME:-}" ]; then
  compose down --volumes --remove-orphans --rmi local || true
fi
python3 .superset/ports.py release "$PWD" || true
exit 0
