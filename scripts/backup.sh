#!/usr/bin/env bash
# Back up the database while the app keeps running; the backups go to data/backups/.
# Needs the backend container running. Options are passed on, for example:
#   scripts/backup.sh --keep-days 30
set -euo pipefail

cd "$(dirname "$0")/.."
docker compose exec -T backend python -m app.backup "$@"
