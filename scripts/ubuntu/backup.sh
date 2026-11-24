#!/usr/bin/env bash
# Back up the database, uploaded/generated files and configuration.
#   sudo bash scripts/ubuntu/backup.sh [target_dir]      (default /var/backups/presales, keeps 30 days)
# Copy the backups to another machine as well (Section 19.4: store backups off the server).
set -euo pipefail

TARGET="${1:-/var/backups/presales}"
KEEP_DAYS="${KEEP_DAYS:-30}"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$APP_DIR/backend/.env"
STAMP=$(date +%Y%m%d-%H%M%S)
DEST="$TARGET/$STAMP"

[[ $EUID -eq 0 ]] || { echo "Run with sudo"; exit 1; }
install -d -m 700 "$DEST"

STORAGE=$(grep -E '^LOCAL_STORAGE_PATH=' "$ENV_FILE" | cut -d= -f2-)
sudo -u postgres pg_dump --format=custom --file=/tmp/presales-$STAMP.dump presales
mv /tmp/presales-$STAMP.dump "$DEST/presales.dump"
if [[ -d "$STORAGE" ]]; then
  (cd "$STORAGE" && zip -qr "$DEST/storage.zip" .)
fi
cp "$ENV_FILE" "$DEST/backend.env"
chmod 600 "$DEST"/*

find "$TARGET" -mindepth 1 -maxdepth 1 -type d -mtime +"$KEEP_DAYS" -exec rm -rf {} +
echo "$(date '+%F %T') backup written to $DEST ($(du -sh "$DEST" | cut -f1))"
