#!/usr/bin/env bash
# Back up the database, then copy the backups elsewhere with rclone. Meant for cron.
# It uses the rclone remote "gdrive"; set RCLONE_REMOTE to use another one.
set -euo pipefail

cd "$(dirname "$0")/.."
remote="${RCLONE_REMOTE:-gdrive}"
daily="$remote:tapo-backups"
monthly="$remote:tapo-monthly"

trap 'echo "Backup or upload FAILED"' ERR

scripts/backup.sh
rclone copy data/backups "$daily" --include 'tapo-*.db.gz' -v
rclone copy data/backups "$monthly" --include 'tapo-??????01-*.db.gz' -v
# Daily copies older than 90 days are deleted for good; the monthly ones are never deleted.
rclone delete "$daily" --min-age 90d --include 'tapo-*.db.gz' --drive-use-trash=false -v
echo "Upload finished"
