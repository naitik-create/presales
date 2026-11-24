#!/usr/bin/env bash
# Restore a backup made by backup.sh (Linux) or backup.ps1 (Windows laptop).
#
#   sudo bash scripts/ubuntu/restore.sh /path/to/backup-folder [--use-env]
#
# The folder must contain presales.dump and optionally storage.zip and backend.env.
# --use-env  also takes SECRETS_ENCRYPTION_KEY from the backup's backend.env, so API keys saved on the
#            old machine can be decrypted here. The database password and paths of this server are kept.
set -euo pipefail

SRC="${1:?Give the backup folder}"
USE_ENV="${2:-}"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$APP_DIR/backend/.env"

[[ $EUID -eq 0 ]] || { echo "Run with sudo"; exit 1; }
[[ -f "$SRC/presales.dump" ]] || { echo "No presales.dump in $SRC"; exit 1; }
read -r -p "This REPLACES the current database and files with the backup. Type RESTORE to continue: " ok
[[ "$ok" == "RESTORE" ]] || { echo "Cancelled"; exit 1; }

echo "== Stopping services"
systemctl stop presales-web presales-api 'presales-worker@*' || true

echo "== Restoring the database"
sudo -u postgres psql -q -c "DROP DATABASE IF EXISTS presales WITH (FORCE);"
sudo -u postgres createdb -O presales_app presales
sudo -u postgres psql -q -d presales -c "CREATE EXTENSION IF NOT EXISTS vector;"
cp "$SRC/presales.dump" /tmp/presales-restore.dump && chmod 644 /tmp/presales-restore.dump
sudo -u postgres pg_restore --no-owner --role=presales_app -d presales /tmp/presales-restore.dump || \
  echo "pg_restore reported warnings (an existing 'vector' extension is expected and harmless)"
rm -f /tmp/presales-restore.dump
sudo -u postgres psql -q -d presales -c "GRANT ALL ON ALL TABLES IN SCHEMA public TO presales_app; GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO presales_app;"

if [[ -f "$SRC/storage.zip" ]]; then
  echo "== Restoring files"
  STORAGE=$(grep -E '^LOCAL_STORAGE_PATH=' "$ENV_FILE" | cut -d= -f2-)
  [[ -d "$STORAGE" ]] && mv "$STORAGE" "$STORAGE.before-restore-$(date +%Y%m%d%H%M%S)"
  install -d -o presales -g presales -m 750 "$STORAGE"
  # Windows archives use backslashes; unzip converts them and returns 1 (warning), which is fine
  unzip -q "$SRC/storage.zip" -d "$STORAGE" || [[ $? -eq 1 ]]
  chown -R presales:presales "$STORAGE"
fi

if [[ "$USE_ENV" == "--use-env" && -f "$SRC/backend.env" ]]; then
  KEY=$(grep -E '^SECRETS_ENCRYPTION_KEY=' "$SRC/backend.env" | tr -d '\r' | cut -d= -f2-)
  if [[ -n "$KEY" ]]; then
    sed -i "s#^SECRETS_ENCRYPTION_KEY=.*#SECRETS_ENCRYPTION_KEY=${KEY}#" "$ENV_FILE"
    echo "== Took SECRETS_ENCRYPTION_KEY from the backup"
  fi
fi

echo "== Applying migrations and starting services"
cd "$APP_DIR/backend"
sudo -u presales .venv/bin/alembic upgrade head
systemctl start presales-api presales-web
for u in /etc/systemd/system/multi-user.target.wants/presales-worker@*.service; do
  [[ -e "$u" ]] && systemctl start "$(basename "$u")"
done
echo "Restore complete."
