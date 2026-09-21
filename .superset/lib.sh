# Sourced by run.sh / teardown.sh from the workspace root.
# Exports this workspace's ports + COMPOSE_PROJECT_NAME and defines compose().
# Exported (not --env-file) so compose still reads .env for ${POSTGRES_USER} etc.
GEN=.superset/.generated
if [ -f "$GEN/ports.env" ]; then
  set -a; . "$GEN/ports.env"; set +a
fi
compose() { docker compose -f docker-compose.yml -f .superset/compose.override.yml "$@"; }
