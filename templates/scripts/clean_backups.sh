#!/usr/bin/env bash
# /var/www/webapp/infrastructure/scripts/clean_backups.sh
# Safely purges database snapshots older than 30 days while retaining at least 5 backups
set -euo pipefail

BACKUP_DIR="/var/lib/meilisearch/snapshots"
RETENTION_DAYS=30
MIN_RETAIN=5

if [ ! -d "$BACKUP_DIR" ]; then
    echo "Backup directory $BACKUP_DIR does not exist. Skipping."
    exit 0
fi

TOTAL_BACKUPS=$(ls -1q "$BACKUP_DIR"/*.snapshot 2>/dev/null | wc -l)

if [ "$TOTAL_BACKUPS" -le "$MIN_RETAIN" ]; then
    echo "Total backups ($TOTAL_BACKUPS) <= minimum retention ($MIN_RETAIN). No backups purged."
    exit 0
fi

echo "Purging snapshots older than $RETENTION_DAYS days in $BACKUP_DIR..."
find "$BACKUP_DIR" -type f -name "*.snapshot" -mtime +$RETENTION_DAYS -exec rm -f {} +
echo "Backup cleanup completed."
