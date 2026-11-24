# Motadata Presales Intelligence Platform

Internal, AI-assisted presales platform for Motadata ObserveOps and ServiceOps (Master Specification v1.3).
Spec Intelligence (Module 1) was removed at the owner's request on 18 Nov 2026; customer contexts remain and are
used by RFP Intelligence and Demo Intelligence.

| Module | Where |
|---|---|
| RFP Intelligence (workspaces, submitted RFP repository, templates) | `/rfp` · `backend/app/modules/rfp` |
| Demo Intelligence (scripts, use-case library) | `/demo` · `backend/app/modules/demo` |
| Ask Motadata (chat, sizing rules, gap log) | `/ask` · `backend/app/modules/ask` |
| Team Scorecard | `/scorecard` · `backend/app/modules/scorecard` |
| Knowledge Hub | `/knowledge` · `backend/app/modules/knowledge` |
| Administration (users, roles, AI models, usage and budget, settings, audit, jobs) | `/admin` · `backend/app/modules/admin` |

Design decisions and open items: [docs/BLUEPRINT.md](docs/BLUEPRINT.md).

## Run on the laptop

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-laptop.ps1 -PostgresPassword <postgres password>   # once
# add ANTHROPIC_API_KEY to backend\.env
powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1
```

Open http://localhost:3000 and sign in as `admin` with the temporary password printed by the seed step.
The API runs on port 8010 (interactive docs at http://127.0.0.1:8010/api/docs outside production).

Optional tools: LibreOffice (`.doc`/`.xls` import, PDF export) and Tesseract OCR (scanned PDFs). Set
`LIBREOFFICE_PATH` and `OCR_ENGINE_PATH` in `backend\.env`.

## Tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

Tests use `TEST_DATABASE_URL` (the `presales_test` database) and never touch the main database.

## Server

* **Ubuntu 24.04:** [docs/UBUNTU-INSTALL.md](docs/UBUNTU-INSTALL.md). Clone to `/opt/presales`, then
  `sudo bash scripts/ubuntu/install.sh` (systemd services, Nginx, PostgreSQL 18, nightly backup).
* **Windows Server:** [docs/SERVER-INSTALL.md](docs/SERVER-INSTALL.md): Windows services via NSSM, firewall, backups.

## Layout

```
backend/   FastAPI app, Alembic migrations, job worker, tests
frontend/  Next.js app (brand tokens in tailwind.config.ts and src/app/globals.css)
scripts/   PowerShell setup, start, server install, backup and restore
docs/      Blueprint and installation guides
```
