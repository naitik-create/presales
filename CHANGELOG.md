# Changelog

Versions follow [Semantic Versioning](https://semver.org/): MAJOR.MINOR.PATCH.
Each release is tagged in git as `vX.Y.Z`; the current version is in the `VERSION` file.

## Unreleased

### Changed
- Administration redesigned: grouped side navigation (People and access, AI, Platform, Monitoring) with a title and
  description for each section; no tab scroll arrows.
- Settings are now forms with labelled fields, units, on/off switches, validation, and Save/Discard per section,
  replacing raw JSON editing. Allowed URL domains are managed as a list.
- Users: search, initials avatars, role chips, and role assignment with switches.
- Roles: access shown as "n of N permissions"; the role editor groups permissions by area with All/None and switches.
- Knowledge Hub sizing rules are edited with a form (input ranges and hardware values) instead of JSON.

## 1.0.0 — 2026-11-18

First release of the Motadata Presales Intelligence Platform (Master Specification v1.3, without Module 1).

### Modules
- **RFP Intelligence**: workspaces, document upload (PDF, Word, Excel, CSV, TXT, ZIP; OCR for scanned PDFs),
  requirement extraction, technical compliance answers with sources, analysis agents (RFP analysis, architecture and
  sizing inputs, risks, PQ/TQ, BOQ, executive synopsis, pre-bid queries), approval, corrigendum and revised-RFP handling,
  placeholder-based proposal templates, Excel/Word/PDF exports, Submitted RFP repository with answer reuse.
- **Demo Intelligence**: curated use-case library with approval, customer-specific demo scripts with unverified-step
  flags, versioning, Word/PDF export, winning scripts saved as templates.
- **Ask Motadata**: cited answers from approved Knowledge Hub sources only, rule-table sizing, feedback and gap log.
- **Team Scorecard**: points ledger with manager approval, immutable records, reversals, warnings, quarterly periods
  and reports.
- **Knowledge Hub**: sections, file upload and registered URLs, approval, versions, duplicate detection,
  permission-filtered retrieval, local or external embeddings with full re-index.
- **Administration**: users, custom roles and granular permissions, AI model per agent, model prices, usage and budget,
  settings, audit log, jobs, **encrypted API keys** (Anthropic, Voyage AI, others) and **logo uploads**.
- Shared customer contexts, global search, notifications, dashboard.

### Platform
- FastAPI + PostgreSQL/pgvector backend with a PostgreSQL job queue; Next.js frontend with Motadata brand tokens.
- Windows setup, service install (NSSM), backup and restore scripts.

### Removed before release
- Spec Intelligence (Module 1) was removed at the owner's request.
