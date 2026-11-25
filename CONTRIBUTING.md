# Working on the Presales Intelligence Platform

This guide is for everyone who changes the code. Read it once before your first pull request.

## Who owns what

| Area | Owner | Folders |
|---|---|---|
| RFP Intelligence | Teammate | `backend/app/modules/rfp`, `backend/app/models/rfp.py`, `frontend/src/app/(app)/rfp`, `backend/app/exports/templates.py`, `frontend/src/components/Templates.tsx` |
| Knowledge Hub, document parsing | Teammate | `backend/app/modules/knowledge`, `backend/app/models/knowledge.py`, `backend/app/parsing`, `frontend/src/app/(app)/knowledge` |
| Ask Motadata, Demo Intelligence, Team Scorecard, Dashboard, Administration, sign-in | Naitik | `backend/app/modules/{ask,demo,scorecard,dashboard,admin,auth,branding,search,customers}` and their frontend pages |
| **Shared foundations** | Naitik (review required) | `backend/app/core`, `backend/app/ai`, `backend/app/models/core.py`, `backend/alembic`, `frontend/src/components/ui.tsx`, `frontend/tailwind.config.ts`, `scripts`, `.github` |

`.github/CODEOWNERS` makes GitHub ask the right person to review automatically.

**Shared code affects every module.** If your change needs something in a shared folder (a new UI component, a change
to Knowledge Hub search in `app/ai/retrieval.py`, a new permission), say so in the pull request or agree it first.
Knowledge Hub search is used by Ask Motadata, RFP Intelligence and Demo Intelligence, so changes to what it stores or
returns must be agreed by both owners.

## Set up your laptop (Windows, once)

Install:
* **Git** — https://git-scm.com
* **Python 3.11 or 3.12** — tick "Add to PATH"
* **Node.js 22 LTS**
* **PostgreSQL 18** with **pgvector** (copy the prebuilt pgvector files into the PostgreSQL folder; see
  `docs/SERVER-INSTALL.md`, "pgvector")

Then in PowerShell:

```powershell
git clone https://github.com/naitik-create/presales.git D:\Presales
cd D:\Presales
powershell -ExecutionPolicy Bypass -File scripts\setup-laptop.ps1 -PostgresPassword <your postgres password>
powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1
```

Open http://localhost:3000 and sign in as `admin` with the temporary password printed by the setup. Your laptop has its
own database; nothing you do locally affects the office server.

To try AI features, add your own Claude key in Administration > API keys (it is stored encrypted in your local database).

If Windows Smart App Control blocks a Python package, see the note on `jiter` in `backend/requirements.txt`.

## Daily workflow

1. **Start from the latest `main`:**
   ```powershell
   git checkout main
   git pull
   git checkout -b rfp/compliance-export      # <module>/<short-description>
   ```
2. Make your change. Commit small, meaningful steps with a clear message, e.g. `RFP: add bulk approve to requirements`.
3. **Before pushing, run the checks:**
   ```powershell
   cd backend;  .\.venv\Scripts\python.exe -m pytest -q
   cd ..\frontend;  npx tsc --noEmit
   ```
4. Add one line under **Unreleased** in `CHANGELOG.md` describing the change for users.
5. Push and open a pull request:
   ```powershell
   git push -u origin rfp/compliance-export
   ```
   GitHub shows a "Compare & pull request" button. Fill in the template, attach a screenshot for UI changes.
6. GitHub runs the automatic checks (backend tests on PostgreSQL 18, frontend type check and build). They must be green.
7. The owner reviews. After approval, merge with **Squash and merge** and delete the branch.
8. Keep your branch up to date while you work: `git pull origin main` (fix any conflicts, run the checks again).

Branch name prefixes: `rfp/`, `knowledge/`, `ask/`, `demo/`, `scorecard/`, `admin/`, `platform/`, `fix/`.

## Database changes (Alembic migrations)

Every change to the database models needs a migration. Two people adding migrations at the same time creates two
"heads", which the automatic check rejects. To avoid it:

1. `git pull origin main` **just before** creating the migration.
2. Change the model, then generate the migration:
   ```powershell
   cd backend
   .\.venv\Scripts\alembic.exe revision --autogenerate -m "rfp: add submission deadline"
   ```
3. Open the generated file in `backend/alembic/versions`, check it does only what you intended, and run
   `.\.venv\Scripts\alembic.exe upgrade head`.
4. One migration per pull request where possible. Never edit a migration that is already on `main`; add a new one.
5. If the check reports two heads after `main` moved on: `alembic merge heads -m "merge"`, commit, push.

Never change audit-log, scoring immutability or permission tables without the platform owner's review.

## Coding conventions

* Match the style of the surrounding code; keep functions small and named plainly.
* Backend: every route declares its permission with `require("area.action")`. Hiding a button is not security.
* Untrusted text (uploaded documents, web pages) goes to the AI wrapped with `doc_block(...)` and is never followed as
  instructions.
* Never store prompts or AI answers in usage logs, and never log secrets.
* Frontend: use the components in `components/ui.tsx` (Button variants, Field, Select, Drawer, Segmented, Tabs,
  Table, Badge/StatusBadge). Use the brand tokens only; no hard-coded colours, font sizes or spacing.
  Primary button = the one main action on a screen; edit forms open in a side panel (`Drawer`).
* Add or update tests for business rules (`backend/tests`).

## Never commit

`backend/.env`, API keys, passwords, customer RFPs or documents, database dumps, `storage/`, `node_modules/`, `.venv/`.
`.gitignore` covers these, but check `git status` before committing.

## Releases and the office server

* Only the platform owner tags releases (`vX.Y.Z`): update `VERSION`, move **Unreleased** in `CHANGELOG.md` under the new
  version, tag and push.
* The office server is updated from GitHub with `sudo bash scripts/ubuntu/update.sh` (or a specific tag). Never edit
  code on the server.
