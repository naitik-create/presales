# Working on the Presales Intelligence Platform

This guide is for everyone who changes the code. Read it once before your first upload.

## Who owns what

| Area | Owner | Folders |
|---|---|---|
| RFP Intelligence | Teammate | `backend/app/modules/rfp`, `backend/app/models/rfp.py`, `frontend/src/app/(app)/rfp`, `backend/app/exports/templates.py`, `frontend/src/components/Templates.tsx` |
| Knowledge Hub, document parsing | Teammate | `backend/app/modules/knowledge`, `backend/app/models/knowledge.py`, `backend/app/parsing`, `frontend/src/app/(app)/knowledge` |
| Ask Motadata, Demo Intelligence, Team Scorecard, Dashboard, Administration, sign-in | Naitik | `backend/app/modules/{ask,demo,scorecard,dashboard,admin,auth,branding,search,customers}` and their frontend pages |
| **Shared foundations** | Naitik (tell him before changing) | `backend/app/core`, `backend/app/ai`, `backend/app/models/core.py`, `backend/alembic`, `frontend/src/components/ui.tsx`, `frontend/tailwind.config.ts`, `scripts`, `.github` |


**Shared code affects every module.** If your change needs something in a shared folder (a new UI component, a change
to Knowledge Hub search in `app/ai/retrieval.py`, a new permission), tell the other person first.
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

## Daily workflow (everyone works on `main`)

We keep it simple: download the latest code, work, upload. The one rule: **always download the latest just before you
upload**, so nobody overwrites anyone else's work.

**Once on each laptop** (download with "rebase" so history stays tidy):
```powershell
git config --global pull.rebase true
git config --global user.name "Your Name"
git config --global user.email "<your GitHub no-reply email, from GitHub > Settings > Emails>"
```

**Every time you start working:**
```powershell
cd D:\Presales
git pull
```
If the other person changed libraries or the database, also run:
```powershell
cd backend;  .\.venv\Scripts\pip.exe install -r requirements.txt;  .\.venv\Scripts\alembic.exe upgrade head
cd ..\frontend;  npm install
```

**When you have finished a piece of work:**
```powershell
cd D:\Presales
cd backend;  .\.venv\Scripts\python.exe -m pytest -q          # tests must pass
cd ..\frontend;  npx tsc --noEmit                              # no type errors
cd ..
git add -A
git status                                                     # check: no .env, no customer files
git commit -m "RFP: add bulk approve to requirements"
git pull                                                       # get the other person's latest work first
git push                                                       # upload
```

* Add one line under **Unreleased** in `CHANGELOG.md` for anything users will notice.
* Commit and push small pieces often (at least daily). Small uploads rarely clash.
* **If `git pull` reports a conflict:** the same lines were changed by both of you. Open the files it lists, keep the
  right version of each marked block (between `<<<<<<<` and `>>>>>>>`), then `git add -A` and `git rebase --continue`,
  then run the tests and `git push`. If unsure, run `git rebase --abort` (nothing is lost) and ask the other person.
* **Never use `git push --force`.** It deletes the other person's uploaded work.
* After each upload GitHub runs the automatic checks (backend tests, frontend type check and build). If they fail you
  get an email: fix it straight away so the other person does not download broken code. Results:
  https://github.com/naitik-create/presales/actions
* Tell the other person before changing shared code (`app/core`, `app/ai`, `ui.tsx`, models) — it affects every module.

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
4. Push a migration as soon as it is ready, and tell the other person. Never edit a migration that is already on `main`; add a new one.
5. If the check reports two heads after `main` moved on: `alembic merge heads -m "merge"`, commit, push.

Never change audit-log, scoring immutability or permission tables without agreeing it with the platform owner.

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
