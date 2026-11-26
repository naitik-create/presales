# Changelog

Versions follow [Semantic Versioning](https://semver.org/): MAJOR.MINOR.PATCH.
Each release is tagged in git as `vX.Y.Z`; the current version is in the `VERSION` file.

## Unreleased

### Added
- RFP Intelligence: **bid synopsis**. RFP analysis now fills 20 tender facts with references (tender no., authority, bid
  type, value, EMD, tender fee, PBG, contract and AMC period, timeline, turnover, experience, certifications, OEM/MAF
  criteria, Make in India, consortium, evaluation method, payment terms, SLA and penalties, LD) plus ranked red flags.
  The analysis report (Word/PDF) and internal workbook open with the bid synopsis.
- RFP Intelligence: **top 10 pre-bid queries in the tender's format**. Queries are ranked by impact on the bid, with
  category, clause details and suggested change; the top 10 are pre-selected. The agent finds the pre-bid query format
  the RFP prescribes (columns and submission instructions) and the new Excel / Word downloads use exactly those columns
  (standard format when the RFP has none). On the Analysis tab, tick which queries to submit, reorder and save.
  Plan for the remaining RFP gaps: `docs/GAP-PLAN.md`.
- Team collaboration: `CONTRIBUTING.md` (module ownership, laptop setup, simple pull-work-push workflow on `main`,
  conflict handling, migration rules, conventions) and GitHub Actions checks after every push (backend tests on
  PostgreSQL 18 with pgvector, single migration head, frontend type check and build).
- Ubuntu 24.04 deployment: `scripts/ubuntu/install.sh` (PostgreSQL 18 + pgvector, Node.js 22, LibreOffice, Tesseract,
  systemd services for API, workers and web, Nginx on port 80 with /api routed straight to the API, firewall rules,
  nightly backup), `update.sh` (backup, pull or check out a release, reinstall, migrate, restart), `backup.sh` and
  `restore.sh` (also restores Windows laptop backups and can carry over the API-key encryption key), and
  `docs/UBUNTU-INSTALL.md`.

### Changed
- Ask Motadata redesigned as a modern assistant: full-height layout with a slim conversation list (New chat,
  recent conversations, delete on hover); a welcome screen with suggested questions; a growing composer with the
  product choice built in (Enter to send, Shift + Enter for a new line); user questions as light bubbles; answers with
  a status badge, formatted lists and bold text, numbered citation markers, limitations, and source cards that open
  the document; copy, helpful and not-helpful actions. The gap log is now "Unanswered questions", reached from the
  conversation list.

## 1.0.2 — 2026-11-19

### Added
- Agents can use models from **OpenAI**, **Google Gemini** and **Azure OpenAI** as well as Anthropic Claude. Models are
  added in Administration > AI models with a provider (and the resource endpoint for Azure), then chosen per agent.
  Calls use each provider's HTTPS API with structured JSON output, retries, usage logging and cost estimates.
  The provider's key comes from Administration > API keys; screens warn when a selected model has no key.
- Connection test for OpenAI and Gemini keys.

### Changed
- Knowledge Hub layout simplified after reviewing it on screen: underlined tabs; four summary tiles (total, approved,
  awaiting approval, failed) that also filter the list; one toolbar row (section dropdown, search, Manage sections);
  a sources table; sections managed in a side panel with on/off switches; proper empty states with action buttons
  for Sources, Approvals and Sizing rules.

### Fixed
- Dropdowns and fields now respect a set width instead of always stretching to full width.
- Usage "This month" started a day early in time zones east of UTC.

### Changed (earlier in this release)
- Knowledge Hub rebuilt: header with Upload file / Add URL; Sources, Approvals (with waiting count), Sizing rules and
  Test search as sub-pages; a quiet section list; a source list with one clear status per source (Processing,
  Failed, Awaiting approval, Approved), status filters with counts, search, live progress and empty states;
  upload with drag-and-drop, URL and new-section forms in side panels; source details in a side panel (facts,
  download / new version / fetch again, approval with note, versions, history); one-click approve or reject in the
  Approvals queue; Test search shows ranked passages with match percentage.
- Usage and budget page rebuilt: date presets (this month, 30 / 90 days, all time) and module/agent/user filters in
  one row; four headline figures; a cost-per-day bar chart with hover details; a monthly budget meter with alert
  markers and status; a cost breakdown by agent, user, module or model with share bars; a slimmer recent-calls log.
  The budget is edited in a side panel (amount, alert thresholds, hard stop). The usage API now returns daily totals.
- Buttons have one distinctive brand style across the application: pill shape (fields stay square-cornered).
  Primary = Motadata accent fill with black text, turning black on hover; secondary = black outline that fills black
  on hover; ghost = light grey pill (darker on hover), so low-emphasis actions still read as buttons;
  danger = error-colour outline. Roles page: New role is primary, Duplicate secondary, Delete danger. Links and upload labels that act
  as buttons use the same styles.
- Minimalist pass across the application: 14px interface text, 32px buttons and fields, slimmer main menu and top
  bar, smaller icons, softer section menu, one heading per admin page, crisper 6px corners, smaller switches.
- Roles and permissions simplified: plain role list, compact permission rows (All / x of y / None), descriptions only
  when a group is expanded, and a save bar that appears only when there are unsaved changes.
- Administration redesigned: grouped side navigation (People and access, AI, Platform, Monitoring) with a title and
  description for each section; no tab scroll arrows.
- Settings are now forms with labelled fields, units, on/off switches, validation, and Save/Discard per section,
  replacing raw JSON editing. Allowed URL domains are managed as a list.
- Users: search, initials avatars, role chips, and role assignment with switches.
- Roles: access shown as "n of N permissions"; the role editor groups permissions by area with All/None and switches.
- Knowledge Hub sizing rules are edited with a form (input ranges and hardware values) instead of JSON.
- AI models: agents grouped by module with plain-language descriptions and summary chips, an on/off switch, a
  Configure dialog (model, effort, output limit, time limit, retries) and "set one model for all agents"; model prices
  with add/edit dialog; embedding options shown as cards.
- API keys: provider cards with connection status (Connected, Not tested, Test failed, Not configured), masked key,
  storage location and test date; other providers in a compact list.
- Roles and permissions rebuilt as a two-pane page: role list on the left (permission and user counts), selected role
  on the right with name and description, collapsible permission groups with a plain description, group checkboxes
  (all / some / none), a permission filter, a Members tab, Duplicate and Delete, and a save bar with unsaved-change
  tracking. Built-in roles cannot be renamed.
- Tables use a light header row instead of solid black.
- AI models page rebuilt: Agents / Models / Embeddings sub-pages; agents in one compact table grouped by module;
  a single "provider not connected" banner with a link to API keys instead of a warning on every agent; editing in a
  side panel; "Change model for all agents" dialog.

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
