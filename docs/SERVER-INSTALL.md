# Windows server installation (Section 19.3)

Moving from the laptop to the server is a configuration change and this documented install. No code changes.

## 1. Prerequisites on the server

| Software | Notes |
|---|---|
| Python 3.11 | Install for all users; tick "Add to PATH" |
| Node.js 20 LTS or later | |
| PostgreSQL 16–18 | Note the `postgres` superuser password |
| pgvector 0.8.x | Copy the prebuilt Windows files for your PostgreSQL version into `C:\Program Files\PostgreSQL\<ver>\lib` and `share\extension` (`vector.dll`, `vector.control`, `vector--*.sql`), then restart PostgreSQL |
| LibreOffice | For `.doc`/`.xls` import and PDF export. Set `LIBREOFFICE_PATH` to `soffice.exe` |
| Tesseract 5 (UB Mannheim build) | English data included. Set `OCR_ENGINE_PATH` to `tesseract.exe` |
| NSSM | Service wrapper, e.g. `C:\Tools\nssm\nssm.exe` |

If the server has no internet access, copy `backend\.model_cache` from the laptop (the local embedding model) and
the `frontend\node_modules` folder, or run the installs once while connected.

Windows Smart App Control can block some Python native modules. `requirements.txt` pins `jiter==0.10.0`,
which loads on machines where newer builds are blocked.

## 2. Install

```powershell
git clone <repository> D:\Presales      # or copy the folder
cd D:\Presales
powershell -ExecutionPolicy Bypass -File scripts\setup-laptop.ps1 -PostgresPassword <pw>
```

Edit `backend\.env`: set `APP_ENV=production`, `LIBREOFFICE_PATH`, `OCR_ENGINE_PATH`.
Keep `.env` readable only by administrators and the service account.

API keys (Anthropic, Voyage AI, others) are entered in **Administration > API keys** and stored encrypted in the
database with `SECRETS_ENCRYPTION_KEY` from `.env`. When moving from the laptop, copy the same
`SECRETS_ENCRYPTION_KEY` (or re-enter the keys); without it the stored keys cannot be decrypted. Logos are uploaded in
**Administration > Branding**.

Then, as Administrator:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-server.ps1 -Nssm C:\Tools\nssm\nssm.exe -Workers 2
```

This creates `PresalesApi` (127.0.0.1:8010), `PresalesWorker1..N` and `PresalesWeb` (port 3000), all set to start
automatically and restart on failure, and opens TCP 3000 on the Domain and Private firewall profiles only.
Team machines open `http://<server-name>:3000`.

## 3. Logs and health

* Logs: `backend\logs\<service>.log`, rotated at 10 MB.
* Health: `http://127.0.0.1:8010/api/health` on the server.
* Jobs: Administration > Jobs shows queued, running and failed jobs with retry and cancel.

## 4. Upgrade and rollback

```powershell
powershell -File scripts\backup.ps1 -Target \\<backup-host>\presales     # always back up first
git pull                                                                  # or copy the new release
powershell -ExecutionPolicy Bypass -File scripts\install-server.ps1 -Nssm C:\Tools\nssm\nssm.exe
```

Rollback: check out the previous release, run `scripts\restore.ps1` with the pre-upgrade backup, then run
`install-server.ps1` again.

## 5. Backup and restore (Section 19.4)

Schedule a daily backup to another disk or machine:

```powershell
schtasks /Create /SC DAILY /ST 01:00 /TN PresalesBackup /RU SYSTEM `
  /TR "powershell -ExecutionPolicy Bypass -File D:\Presales\scripts\backup.ps1 -Target \\nas\backups\presales"
```

Each backup holds `presales.dump` (database), `storage.zip` (uploaded, knowledge and generated files) and
`backend.env` (configuration). Restore with `scripts\restore.ps1 -Source <backup folder> -PostgresPassword <pw>`
after stopping the services. Test a restore at least once before go-live.

## 6. Before any public access

HTTPS and a second login factor are required first (Section 17). Do not expose port 3000 to the internet.
