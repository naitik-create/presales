#!/usr/bin/env bash
# Install or update the Motadata Presales Intelligence Platform on Ubuntu 24.04.
#
#   cd /opt/presales && sudo bash scripts/ubuntu/install.sh
#
# Safe to run again: existing configuration, database and files are kept.
# Installs: PostgreSQL 18 + pgvector, Python venv, Node.js 22, LibreOffice, Tesseract, Nginx,
# systemd services (presales-api, presales-worker@1..N, presales-web) and a nightly backup.
set -euo pipefail
trap 'printf "\n\033[31mERROR: the installer stopped at line %s: %s\033[0m\nFix the problem above and run the installer again; it is safe to repeat.\n" "$LINENO" "$BASH_COMMAND" >&2' ERR

APP_USER="presales"
DATA_DIR="/var/lib/presales"
BACKUP_DIR="/var/backups/presales"
WORKERS="${WORKERS:-2}"
PG_VERSION=18
API_PORT=8010
WEB_PORT=3000

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND="$APP_DIR/backend"
FRONTEND="$APP_DIR/frontend"
ENV_FILE="$BACKEND/.env"

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
# Random letters and digits. (Not "tr </dev/urandom | head": with pipefail, tr's SIGPIPE ends the script silently.)
rand() { python3 -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range($1)))"; }
fail() { printf '\n\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || fail "Run with sudo: sudo bash scripts/ubuntu/install.sh"
. /etc/os-release
[[ "${ID:-}" == "ubuntu" ]] || fail "This script is for Ubuntu (found ${ID:-unknown})"
[[ "${VERSION_ID:-}" == "24.04" ]] || echo "Warning: tested for Ubuntu 24.04, found ${VERSION_ID:-unknown}"
[[ -f "$BACKEND/requirements.txt" && -f "$FRONTEND/package.json" ]] || fail "Run this from inside the cloned repository"

# ---------------------------------------------------------------- packages
say "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q ca-certificates curl gnupg git lsb-release \
  python3 python3-venv python3-dev build-essential \
  nginx ufw cron unzip zip \
  libreoffice-writer-nogui libreoffice-calc-nogui \
  tesseract-ocr tesseract-ocr-eng

if [[ ! -f /etc/apt/sources.list.d/pgdg.list ]]; then
  say "Adding the official PostgreSQL repository"
  install -d /usr/share/postgresql-common/pgdg
  curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc
  echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
    > /etc/apt/sources.list.d/pgdg.list
  apt-get update -q
fi
apt-get install -y -q "postgresql-${PG_VERSION}" "postgresql-${PG_VERSION}-pgvector"
systemctl enable --now postgresql

# The app gets its own PostgreSQL 18 cluster. If another PostgreSQL already uses 5432 (for example a
# PostgreSQL 16 used by other software), Ubuntu does not create the 18 cluster, so create it on the next free port.
# Existing clusters are never changed.
CLUSTER=$(pg_lsclusters -h | awk -v v="$PG_VERSION" '$1==v && $2=="main"')
if [[ -z "$CLUSTER" ]]; then
  port=5432
  while [[ -n "$(ss -ltnH "sport = :$port")" ]]; do port=$((port + 1)); done
  say "Creating a PostgreSQL ${PG_VERSION} cluster for this application on port ${port}"
  pg_createcluster "$PG_VERSION" main --port "$port" --start
fi
PG_PORT=$(pg_lsclusters -h | awk -v v="$PG_VERSION" '$1==v && $2=="main" {print $3}')
pg_ctlcluster "$PG_VERSION" main start 2>/dev/null || true
systemctl enable "postgresql@${PG_VERSION}-main" >/dev/null 2>&1 || true
[[ "$(pg_lsclusters -h | awk -v v="$PG_VERSION" '$1==v && $2=="main" {print $4}')" == "online" ]] \
  || fail "PostgreSQL ${PG_VERSION} did not start. See /var/log/postgresql/postgresql-${PG_VERSION}-main.log"
echo "PostgreSQL ${PG_VERSION} cluster is online on port ${PG_PORT}"
PSQL=(sudo -u postgres psql -p "$PG_PORT")

NODE_MAJOR=$(node -v 2>/dev/null | sed -E 's/^v([0-9]+).*/\1/' || echo 0)
if [[ "${NODE_MAJOR:-0}" -lt 20 ]]; then
  say "Installing Node.js 22 LTS"
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y -q nodejs
fi
echo "Python $(python3 --version | cut -d' ' -f2), Node $(node -v), PostgreSQL ${PG_VERSION}"

# ---------------------------------------------------------------- user and folders
say "Creating the service account and folders"
id "$APP_USER" &>/dev/null || useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin "$APP_USER"
install -d -o "$APP_USER" -g "$APP_USER" -m 750 "$DATA_DIR" "$DATA_DIR/storage" "$DATA_DIR/model_cache" "$DATA_DIR/npm-cache"
install -d -o root -g root -m 700 "$BACKUP_DIR"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
git config --system --add safe.directory "$APP_DIR" 2>/dev/null || true

# ---------------------------------------------------------------- database
say "Preparing the database"
if [[ -f "$ENV_FILE" ]]; then
  DB_URL=$(grep -E '^DATABASE_URL=' "$ENV_FILE" | cut -d= -f2-)
  DB_PASS=$(sed -E 's#^[^:]+://[^:]+:([^@]+)@.*#\1#' <<<"$DB_URL")
else
  DB_PASS=$(rand 32)
fi
"${PSQL[@]}" -v ON_ERROR_STOP=1 -q <<SQL
DO \$\$BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'presales_app') THEN
    CREATE ROLE presales_app LOGIN PASSWORD '${DB_PASS}';
  ELSE
    ALTER ROLE presales_app LOGIN PASSWORD '${DB_PASS}';
  END IF;
END\$\$;
SQL
if [[ "$("${PSQL[@]}" -tAc "SELECT 1 FROM pg_database WHERE datname='presales'")" != "1" ]]; then
  sudo -u postgres createdb -p "$PG_PORT" -O presales_app presales
fi
"${PSQL[@]}" -q -d presales -c "CREATE EXTENSION IF NOT EXISTS vector;"

# ---------------------------------------------------------------- python
say "Installing the backend (Python)"
sudo -u "$APP_USER" python3 -m venv "$BACKEND/.venv"
sudo -u "$APP_USER" "$BACKEND/.venv/bin/pip" install -q --upgrade pip
sudo -u "$APP_USER" "$BACKEND/.venv/bin/pip" install -q -r "$BACKEND/requirements.txt"

# ---------------------------------------------------------------- configuration
if [[ ! -f "$ENV_FILE" ]]; then
  say "Writing backend/.env"
  SECRET=$(rand 48)
  FERNET=$("$BACKEND/.venv/bin/python" -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
  cat > "$ENV_FILE" <<ENV
APP_ENV=production
APP_NAME=Motadata Presales Intelligence Platform
APP_SECRET_KEY=${SECRET}
DATABASE_URL=postgresql+psycopg://presales_app:${DB_PASS}@localhost:${PG_PORT}/presales
# Encrypts API keys saved in Administration > API keys. Back this file up:
# without this key the stored API keys cannot be decrypted.
SECRETS_ENCRYPTION_KEY=${FERNET}
ANTHROPIC_API_KEY=
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=${DATA_DIR}/storage
EMBEDDING_PROVIDER=local
EXTERNAL_EMBEDDING_API_KEY=
MODEL_CACHE_PATH=${DATA_DIR}/model_cache
LIBREOFFICE_PATH=/usr/bin/soffice
OCR_ENGINE_PATH=/usr/bin/tesseract
MAX_CONCURRENT_RFP_JOBS=2
MAX_QUEUED_RFP_JOBS=20
WORKER_COUNT=${WORKERS}
AUTH_PROVIDER=local
URL_FETCH_ALLOWED_DOMAINS=motadata.com,docs.motadata.com
ENV
else
  echo "Keeping existing backend/.env"
fi
chown "$APP_USER:$APP_USER" "$ENV_FILE"
chmod 600 "$ENV_FILE"

# ---------------------------------------------------------------- schema and first admin
say "Applying database migrations"
cd "$BACKEND"
sudo -u "$APP_USER" .venv/bin/alembic upgrade head
SEED_OUT=$(sudo -u "$APP_USER" .venv/bin/python -m app.seed)
echo "$SEED_OUT"

say "Downloading the local embedding model (one time)"
sudo -u "$APP_USER" HF_HUB_DISABLE_SYMLINKS_WARNING=1 .venv/bin/python - <<'PY' || echo "Warning: model download failed; it will be retried on first use."
from app.config import get_settings
from app.ai.embeddings import OPTIONS
from fastembed import TextEmbedding
TextEmbedding(model_name=OPTIONS["local"]["model_name"], cache_dir=str(get_settings().model_cache_path))
print("Embedding model ready")
PY

# ---------------------------------------------------------------- frontend
say "Building the web application (this takes a few minutes)"
cd "$FRONTEND"
sudo -u "$APP_USER" env npm_config_cache="$DATA_DIR/npm-cache" npm ci --no-audit --no-fund
sudo -u "$APP_USER" env npm_config_cache="$DATA_DIR/npm-cache" BACKEND_URL="http://127.0.0.1:${API_PORT}" NEXT_TELEMETRY_DISABLED=1 npm run build

# ---------------------------------------------------------------- services
say "Installing systemd services"
NODE_BIN=$(command -v node)
cat > /etc/systemd/system/presales-api.service <<UNIT
[Unit]
Description=Presales Intelligence API
After=network.target postgresql.service
Requires=postgresql.service

[Service]
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${BACKEND}
Environment=HF_HUB_DISABLE_SYMLINKS_WARNING=1
ExecStart=${BACKEND}/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port ${API_PORT} --workers 2 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/presales-worker@.service <<UNIT
[Unit]
Description=Presales Intelligence job worker %i
After=network.target postgresql.service
Requires=postgresql.service

[Service]
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${BACKEND}
Environment=HF_HUB_DISABLE_SYMLINKS_WARNING=1
ExecStart=${BACKEND}/.venv/bin/python worker.py
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/presales-web.service <<UNIT
[Unit]
Description=Presales Intelligence web application
After=network.target presales-api.service

[Service]
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${FRONTEND}
Environment=NODE_ENV=production
Environment=NEXT_TELEMETRY_DISABLED=1
ExecStart=${NODE_BIN} node_modules/next/dist/bin/next start -H 127.0.0.1 -p ${WEB_PORT}
Restart=always
RestartSec=5
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable presales-api presales-web >/dev/null
systemctl restart presales-api presales-web
for i in $(seq 1 "$WORKERS"); do
  systemctl enable "presales-worker@$i" >/dev/null
  systemctl restart "presales-worker@$i"
done

# ---------------------------------------------------------------- nginx
say "Configuring Nginx"
cat > /etc/nginx/sites-available/presales <<NGINX
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    client_max_body_size 110m;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy same-origin always;

    # API straight to FastAPI (large uploads and long AI calls)
    location /api/ {
        proxy_pass http://127.0.0.1:${API_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_request_buffering off;
    }

    location / {
        proxy_pass http://127.0.0.1:${WEB_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINX
ln -sf /etc/nginx/sites-available/presales /etc/nginx/sites-enabled/presales
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable nginx >/dev/null
systemctl reload nginx || systemctl restart nginx

# ---------------------------------------------------------------- firewall
say "Firewall"
ufw allow OpenSSH >/dev/null
ufw allow 'Nginx HTTP' >/dev/null
if [[ "$(ufw status)" == *"Status: active"* ]]; then
  echo "ufw is active: SSH and HTTP (80) are allowed."
else
  echo "ufw is not active. Rules for SSH and HTTP are added; turn it on with: sudo ufw enable"
fi

# ---------------------------------------------------------------- backups
say "Scheduling the nightly backup"
cat > /etc/cron.d/presales-backup <<CRON
# Nightly backup of the Presales database, files and configuration (keeps 30 days)
0 1 * * * root bash ${APP_DIR}/scripts/ubuntu/backup.sh ${BACKUP_DIR} >> /var/log/presales-backup.log 2>&1
CRON
chmod 644 /etc/cron.d/presales-backup

# ---------------------------------------------------------------- check
say "Checking the installation"
ok=0
for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1/api/health" >/dev/null 2>&1 && curl -fsS -o /dev/null "http://127.0.0.1/login"; then ok=1; break; fi
  sleep 2
done
systemctl --no-pager --plain list-units 'presales-*' | sed -n '1,10p'
IP=$(hostname -I | awk '{print $1}')
if [[ $ok -eq 1 ]]; then
  say "Done. Open http://${IP}/ from a computer on the office network."
else
  echo "The services did not answer yet. Check: sudo journalctl -u presales-api -u presales-web -n 50"
fi
if grep -q "temporary password" <<<"$SEED_OUT"; then
  echo
  echo "$SEED_OUT" | grep "temporary password"
  echo "Sign in as 'admin' with this password; you will be asked to set a new one."
fi
