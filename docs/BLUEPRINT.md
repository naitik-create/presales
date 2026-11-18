# Implementation Blueprint — Motadata Presales Intelligence Platform

Derived from Master Specification v1.3. Section numbers (§) refer to that document.

> **18 Nov 2026: Spec Intelligence (Module 1, §7) removed at the owner's request.** Its tables, permissions, agents and UI are gone (migration `b7c8d9e0f1a2`). Consequences: RFP Intelligence no longer pre-fills answers from verified clause checks (§8.8) or produces the seeded-versus-published comparison (§7.12); compliance sources are now approved documentation and internal knowledge, then past submitted RFP answers. Demo use cases no longer carry a POC flag. The size parser moved to `app/common/sizes.py` and still fills customer context sizes. Items below that concern Module 1 are obsolete.

## 1. Architecture

Modular monolith (§4.1): one FastAPI backend, one Next.js frontend, one PostgreSQL database, plus worker processes that consume a PostgreSQL job queue.

```
Browser ──HTTP──> Next.js (port 3000) ──/api proxy──> FastAPI (port 8010) ──> PostgreSQL + pgvector
                                                          │                       ▲
                                                          └── Claude API          │
                                         worker.py (N processes) ─────────────────┘
```

* The browser only talks to Next.js; Next.js rewrites `/api/*` to the backend, so cookies are same-origin and the Claude key never leaves the server.
* Each module is a package under `backend/app/modules/<name>` with its own `routes.py`, `service.py` and models in `backend/app/models/<group>.py`.

## 2. Repository layout

```
backend/
  app/
    main.py            FastAPI app, router registration, startup validation
    config.py          Settings from environment (.env); fails fast on missing values
    db.py              Engine, session, Base
    core/              security, permissions catalogue, deps, audit, storage, jobs, notifications
    ai/                Claude client wrapper (usage logging, per-agent config), embeddings, retrieval
    parsing/           File-to-text extraction (PDF, DOCX, XLSX, CSV, TXT, MD, OCR, LibreOffice)
    models/            SQLAlchemy models by group (§15)
    modules/           auth, admin, knowledge, ask, customers, spec, rfp, demo, scorecard, search, dashboard
    seed.py            Default roles, sections, Spec Pack configuration, demo use cases
  alembic/             Migrations
  tests/               pytest (engine unit tests + API tests on presales_test DB)
  worker.py            Job worker entry point
frontend/              Next.js 15, React 19, TypeScript, Tailwind 3, shadcn-style components
scripts/               PowerShell: setup-laptop.ps1, install-server.ps1, backup.ps1, restore.ps1
docs/                  This blueprint, setup and server guides
```

## 3. Open technical decisions (§24.1) — proposed

| Decision | Choice | Reason |
|---|---|---|
| PostgreSQL job queue | In-house table `job_queue` with `SELECT … FOR UPDATE SKIP LOCKED` | ~80 lines, no extra dependency, survives restart, runs natively on Windows |
| Local embedding model | `BAAI/bge-small-en-v1.5` via **fastembed** (ONNX, 384-dim) | No PyTorch, CPU-only, Windows wheels, good English retrieval |
| External embedding service | Voyage AI `voyage-3` (1024-dim) over HTTPS | Anthropic's recommended embedding partner |
| OCR engine | Tesseract 5 (UB Mannheim Windows build) via `pytesseract`, pages rendered with `pypdfium2` | Free, English model bundled, no Ghostscript needed |
| Word / Excel generation | `python-docx` (placeholder `{{name}}` templates) and `openpyxl` (styled workbooks) | Mature, pure Python |
| Windows service wrapper | **NSSM** | Simple, supports auto-restart and log rotation |
| pgvector on Windows | Prebuilt pgvector 0.8.x binaries copied into PostgreSQL 18 (already present on the laptop) | No Visual Studio build needed |

Embedding dimension differs between models, so `document_chunks.embedding` uses an untyped `vector` column and every row stores `embedding_model` and `embedding_dim`; search filters by the active model (§5.3).

## 4. Data model notes

* The nine Spec Pack configuration tables of Section 15 are held as one `spec_config` table, one JSON row per rule set (industries, module roles, compliance clauses, competitors, win types, PQ areas, tier and posture thresholds, evaluation marks, defaults). Edits are audited.
* Opportunity inputs, scores, competitors and module overrides live on `spec_packs.inputs`; assembled clauses with frozen numbers live on `spec_pack_versions.result`.
* The backend listens on 8010 because 8000 is in use on the development laptop.

## 5. Security design

* Passwords: Argon2id. Sessions: random 256-bit token in an HttpOnly, SameSite=Lax cookie; only a SHA-256 hash is stored in `sessions`. Configurable expiry and lock-out after N failed attempts.
* CSRF: state-changing requests must carry the `X-Requested-With: presales` header (custom header cannot be sent cross-site without CORS, which is disabled).
* Every route declares `Depends(require("area.action"))`. A new user has no roles and therefore no permissions.
* Audit log and approved scoring transactions are protected by PostgreSQL triggers that reject UPDATE and DELETE, so not even an administrator can change them through the application.
* Uploaded and fetched text is wrapped in `<document>` tags with a system instruction that its content is data only (§5.4, §17).
* Scoring tables are never queried by search or AI services.

## 6. Status colours (proposal, §18.4)

| Status | Colour | Contrast on white |
|---|---|---|
| Success | `#1E7A46` | 5.6:1 |
| Warning | `#8A5A00` | 6.1:1 |
| Error | `#B3261E` | 6.5:1 (clearly darker and bluer than accent #F17463) |
| Information | `#1F5FAD` | 6.3:1 |

Each status is shown with a Lucide icon and a text label.

## 7. Items pending owner input

* **Spec Pack Builder Technical Design** — size-parser keyword lists and clause classification order (§7.1, §7.4). A provisional keyword list is in `app/modules/spec/parser.py` and `classifier.py`, marked `PENDING-TD`.
* **Prototype five preset examples** — tests in `tests/test_spec_engine.py` use examples derived from the spec rules; replace with the prototype's presets once supplied.
* **Logo SVGs** — placeholder wordmark in `frontend/public/brand/`; replace files with the same names.
* **Posture A, Tier L/XL — allocation of the 10 freed marks (§7.10)** — currently added to "Compliance to TQ"; configurable in Spec configuration.
* All content (§24.2) is loaded through the application after installation.

## 8. Phase plan

Phases 1–10 as §21. This build delivers code for all phases; checkpoints remain the owner's validation gates.
