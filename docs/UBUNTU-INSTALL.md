# Installing on Ubuntu 24.04 (office network)

This guide installs the platform on an Ubuntu 24.04 server and makes it available at `http://<server-ip>/` on the
office network. One script does the work; these steps tell you what to run and what to expect.

**What gets installed:** PostgreSQL 18 with pgvector, Python virtual environment, Node.js 22, LibreOffice (for .doc/.xls
and PDF export), Tesseract OCR (for scanned PDFs), Nginx, three kinds of systemd service, and a nightly backup.

| Item | Location |
|---|---|
| Application code | `/opt/presales` (the cloned repository) |
| Configuration and secrets | `/opt/presales/backend/.env` (readable by the service account only) |
| Uploaded and generated files | `/var/lib/presales/storage` |
| Embedding model | `/var/lib/presales/model_cache` |
| Backups | `/var/backups/presales` (nightly at 01:00, kept 30 days) |
| Services | `presales-api` (port 8010, local only), `presales-worker@1`, `presales-worker@2`, `presales-web` (port 3000, local only), `nginx` (port 80) |

---

## Before you start

* Ubuntu **24.04** server with at least **4 CPU, 8 GB RAM, 50 GB free disk** (more disk if you will store many RFPs).
* A user on the server that can run `sudo`.
* **Internet access** on the server during installation (packages, Node.js, Python libraries and the embedding model,
  about 1.5 GB in total). After installation the only outbound traffic needed is to the AI provider (e.g. `api.anthropic.com`).
* A fixed IP address (or DNS name) for the server on the office network, so people can bookmark it.

## Step 1. Create a GitHub access token (the repository is private)

The server needs read access to `github.com/naitik-create/presales`.

1. On GitHub, open **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Name: `presales-server`. Expiration: your choice (e.g. 1 year).
3. **Repository access:** *Only select repositories* → `naitik-create/presales`.
4. **Permissions → Repository permissions → Contents: Read-only.** Nothing else.
5. Generate and copy the token (it starts with `github_pat_`). You will paste it as the password in Step 2.

## Step 2. Download the code

Connect to the server (SSH) and run:

```bash
sudo apt update && sudo apt install -y git
sudo git clone https://github.com/naitik-create/presales.git /opt/presales
```

When asked: **Username** = your GitHub username, **Password** = the token from Step 1.

This gives you the latest code on `main`. To pin the server to a release instead, check out its tag (only releases
made after these Ubuntu scripts were added contain them, so use a tag newer than v1.0.2):

```bash
cd /opt/presales
sudo git tag                     # list releases
sudo git checkout v1.0.3         # example: the newest release tag
cat VERSION
```

## Step 3. Run the installer

```bash
cd /opt/presales
sudo bash scripts/ubuntu/install.sh
```

It takes about 10–20 minutes. At the end it prints, for example:

```
== Done. Open http://192.168.1.50/ from a computer on the office network.
Created user 'admin' with temporary password: Adm-xxxxxxxxxxxx
```

**Copy the admin password now**; it is shown only on the first installation.

Optional: to run three background workers instead of two, use `sudo WORKERS=3 bash scripts/ubuntu/install.sh`.

## Step 4. Turn on the firewall

The installer adds rules for SSH (22) and HTTP (80) but does not switch the firewall on, so it cannot lock you out.

```bash
sudo ufw status            # shows the rules
sudo ufw enable            # turn it on (SSH stays allowed)
```

Ports 3000 and 8010 only listen on the server itself and are not reachable from the network.

## Step 5. First sign-in and setup

1. From any office computer open `http://<server-ip>/` and sign in as **admin** with the temporary password.
2. Set a new password when asked.
3. **Administration → API keys → Anthropic Claude → Add key**, paste the Claude API key, then **Test connection**.
4. **Administration → Branding:** upload the official logos.
5. **Administration → Users:** create accounts for the team and assign roles.
6. **Knowledge Hub:** upload documents and approve them.

---

## Moving data from the Windows laptop (optional)

If you already have content on the laptop, bring it across instead of starting empty.

1. On the **laptop** (PowerShell, as administrator), make a backup:
   ```powershell
   powershell -ExecutionPolicy Bypass -File D:\Presales\scripts\backup.ps1 -Target D:\presales-export
   ```
   This creates a folder such as `D:\presales-export\20261124-101500` with `presales.dump`, `storage.zip` and `backend.env`.
2. Copy that folder to the server, e.g. with WinSCP, or from PowerShell:
   ```powershell
   scp -r D:\presales-export\20261124-101500 youruser@<server-ip>:/tmp/presales-import
   ```
3. On the **server**:
   ```bash
   cd /opt/presales
   sudo bash scripts/ubuntu/restore.sh /tmp/presales-import --use-env
   ```
   Type `RESTORE` to confirm. `--use-env` copies the laptop's `SECRETS_ENCRYPTION_KEY`, so API keys saved on the laptop
   keep working. Users, passwords, documents, workspaces and settings come across as they were.
4. Delete the copy: `sudo rm -rf /tmp/presales-import`.

The laptop and server both use PostgreSQL 18, so the backup restores directly.

---

## Updating to a new version

```bash
cd /opt/presales
sudo bash scripts/ubuntu/update.sh            # latest code on main
sudo bash scripts/ubuntu/update.sh v1.0.3     # or a specific release
```

The update script backs up first, downloads the code (GitHub asks for the username and token again), installs any new
libraries, updates the database, rebuilds the web application and restarts the services. Configuration and data are kept.

To avoid typing the token on every update, store it on the server (it is saved in plain text in `/root/.git-credentials`):

```bash
sudo git config --global credential.helper store
```

**Rolling back:** run `update.sh` with the previous release tag. If the new version changed the database, also restore the
backup that `update.sh` made just before updating (`/var/backups/presales/<date-time>`), using `restore.sh`.

## Backups

* Automatic every night at 01:00 to `/var/backups/presales/<date-time>/` (database, files, configuration); older than
  30 days are removed. Log: `/var/log/presales-backup.log`.
* On demand: `sudo bash /opt/presales/scripts/ubuntu/backup.sh`
* **Copy backups off the server** (a NAS or another machine). A backup on the same disk does not protect against a
  disk failure. For example, add to `/etc/cron.d/presales-backup`:
  `30 1 * * * root rsync -a /var/backups/presales/ backupuser@nas:/backups/presales/`
* `backend.env` inside each backup holds the database password and the API-key encryption key. Keep backups private.
* Test a restore at least once before go-live (`restore.sh` on a test server).

## Everyday operations

| Task | Command |
|---|---|
| Status of all services | `systemctl status 'presales-*' nginx` |
| Restart everything | `sudo systemctl restart presales-api presales-web 'presales-worker@*'` |
| API log (live) | `sudo journalctl -u presales-api -f` |
| Worker log (uploads, RFP jobs) | `sudo journalctl -u 'presales-worker@*' -f` |
| Web log | `sudo journalctl -u presales-web -n 100` |
| Health check | `curl http://127.0.0.1/api/health` |
| Installed version | `cat /opt/presales/VERSION` |
| Edit configuration | `sudo nano /opt/presales/backend/.env`, then restart the services |

## Troubleshooting

| Symptom | What to check |
|---|---|
| Browser shows "502 Bad Gateway" | A service is down: `systemctl status presales-api presales-web`; look at its log. |
| Sign-in page loads but sign-in fails with an error | `sudo journalctl -u presales-api -n 50` (often a database problem). |
| Uploads stay at "Processing" | Workers: `systemctl status 'presales-worker@*'` and their log. |
| "Ingestion failed: no text and OCR is not configured" | `tesseract --version`; reinstall with `sudo apt install tesseract-ocr tesseract-ocr-eng`. |
| AI answers fail | Administration → API keys → Test connection; the server must reach `api.anthropic.com` on port 443. |
| Upload rejected as too large | Default limit is 100 MB per file (`MAX_UPLOAD_MB` in `.env`, and `client_max_body_size` in `/etc/nginx/sites-available/presales`). |
| Install stopped half-way | Fix the reported problem and run `sudo bash scripts/ubuntu/install.sh` again; it is safe to repeat. |

## Security notes

* The application is for the office network only. It runs over plain HTTP on port 80, which the specification allows on
  the local network. **Before any access from outside the office, add HTTPS and a second sign-in factor (Section 17).**
* Only ports 22 and 80 are open. The API (8010), web server (3000) and PostgreSQL (5432) listen on the server only.
* The application runs as the unprivileged `presales` account; `.env` is readable only by that account.
* Change the admin password at first sign-in and give each person their own account.

## Removing the application

```bash
sudo systemctl disable --now presales-api presales-web 'presales-worker@*'
sudo rm /etc/systemd/system/presales-*.service /etc/nginx/sites-enabled/presales /etc/cron.d/presales-backup
sudo systemctl daemon-reload && sudo systemctl reload nginx
# Data, kept until you delete it yourself:
#   sudo -u postgres dropdb presales ; sudo rm -rf /var/lib/presales /opt/presales /var/backups/presales
```
