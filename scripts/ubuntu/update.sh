#!/usr/bin/env bash
# Update to the latest version from GitHub, or to a tagged release.
#
#   cd /opt/presales && sudo bash scripts/ubuntu/update.sh            # latest on main
#   cd /opt/presales && sudo bash scripts/ubuntu/update.sh v1.0.2     # a specific release
#
# Takes a backup first, then pulls, reinstalls dependencies, migrates the database, rebuilds and restarts.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TARGET="${1:-}"
[[ $EUID -eq 0 ]] || { echo "Run with sudo"; exit 1; }

echo "== Backing up before the update"
bash "$APP_DIR/scripts/ubuntu/backup.sh" /var/backups/presales

echo "== Fetching code (GitHub may ask for your username and access token)"
cd "$APP_DIR"
git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true
git fetch --tags origin
if [[ -n "$TARGET" ]]; then
  git checkout "$TARGET"
else
  git checkout main
  git pull --ff-only origin main
fi
echo "Now at: $(git describe --tags --always) (version $(cat VERSION 2>/dev/null || echo '?'))"

# install.sh is safe to re-run: it keeps .env, data and the database
bash "$APP_DIR/scripts/ubuntu/install.sh"
