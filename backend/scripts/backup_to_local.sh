#!/bin/bash
# Quarterly local backup download — TASK-102b
# Run manually: bash backend/scripts/backup_to_local.sh
# See docs/runbooks/quarterly-backup.md for schedule and drill instructions
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/Flashcard-planet-backups}"
DATE=$(date -u +%Y-%m-%d)
QUARTER_DIR="$BACKUP_DIR/$DATE"

mkdir -p "$QUARTER_DIR"

echo "Downloading latest backup from ivancjz/flashcard-planet-backups..."
gh release download \
  --repo ivancjz/flashcard-planet-backups \
  --pattern '*.sql.gz' \
  --dir "$QUARTER_DIR" \
  --clobber

echo "Verifying download..."
ACTUAL_BYTES=$(stat -f%z "$QUARTER_DIR"/*.sql.gz 2>/dev/null || stat -c%s "$QUARTER_DIR"/*.sql.gz)
if [ "$ACTUAL_BYTES" -lt 51200 ]; then
  echo "ERROR: downloaded file is only ${ACTUAL_BYTES} bytes — may be corrupt"
  exit 1
fi

# Remove local copies older than 1 year (365 days)
find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +365 -exec rm -rf {} \; 2>/dev/null || true

echo ""
echo "Done. Backup saved to: $QUARTER_DIR"
ls -lh "$QUARTER_DIR"
echo ""
echo "To restore, see: docs/runbooks/disaster-recovery.md"
