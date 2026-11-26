# RFP Intelligence — gap build plan

Draft 1 · 2026-11-25 · against `main` at `61cdf4c` (v1.0.2 + unreleased)

Goal: upload an RFP → synopsis, Motadata scope, top 10 pre-bid queries in the tender's own format, compliance, hardware
sizing, unpriced SW + HW BOQ → review the bid figures → **one click** for the full bid pack → chat to ask about or change it.

Most of the pipeline exists (`backend/app/modules/rfp/service.py`: extraction → requirements → compliance → 7 document
agents → exports). The work below adds to it; nothing is rewritten.

## Gaps and how each is closed

### G1. Richer synopsis (Bid synopsis)
Today `ANALYSIS_SCHEMA` gives summary, scope, dates, mandatory conditions. Presales needs the tender facts at a glance.
* Extend `ANALYSIS_SCHEMA` with: tender no., authority, bid type (GeM / e-proc / manual), EMD, PBG, tender fee,
  contract period, AMC/warranty years, eligibility (turnover, experience, certifications), OEM criteria (MAF, Make in
  India class, OEM turnover, OEM presence), payment terms, SLA and penalty caps, LD, evaluation method (L1 / QCBS
  weights), red flags. Every field carries an RFP reference.
* Word export: a one-page "Bid synopsis" first, then the existing detail.
* Later: push tender no., due date, EMD to Bid Tracker (172.16.12.103:5055).

### G2. Motadata scope mapping (new)
* Add `scope_owner` (Motadata / Partner-SI / Customer / Out of scope) and `module` (NMS, Log, Flow, APM, NCM, IPAM,
  ITSM, Asset, Patch, Vulnerability, …) to the **existing compliance call** (`COMPLIANCE_SCHEMA`), so it costs no extra
  AI run. New columns on `rfp_compliance_responses` (migration).
* New document agent `scope_summary`: modules in scope, items for the partner (hardware, OS/DB licences, FMS
  manpower, cabling, third-party tools), customer prerequisites, exclusions, and anything Motadata cannot do.
* Reads a new Knowledge Hub section **Motadata profile** (module list, standard exclusions, standard deviations,
  partner scope, certifications) that you maintain.
* UI: Scope tab with module chips and a filterable matrix. Export: `Scope matrix.xlsx`.

### G3. Top 10 pre-bid queries in the tender's format
* `PREBID_SCHEMA` gains `rank`, `impact` (High/Medium/Low), `category` (Restrictive / competitor-favouring spec,
  PQ or eligibility relaxation, MAF / OEM clause, sizing or quantity unclear, scope unclear, SLA / penalty, payment
  terms, timeline, other) and a `suggested_change`. The prompt ranks by bid impact and the top 10 are marked; the rest
  stay visible as "more".
* New agent `prebid_format`: finds the pre-bid query format annexure in the RFP and returns its exact column headings
  and any instructions (Excel only, font, email address, last date). If none, use the standard format:
  `Sl. No. | RFP Volume/Section | Page No. | Clause No. | Existing clause | Clarification sought | Justification`.
* Queries are mapped onto those columns; export as Excel and Word in that exact layout.
* Past queries that worked: new Knowledge Hub section **Pre-bid queries** (import your old sheets) used as examples of
  tone and of the asks that succeeded.
* UI: drag to reorder, tick which 10 go out, edit inline.

### G4. Hardware sizing from the real Motadata rules
The current rule table (`SizingRule`: input ranges → one result) cannot express the ObserveOps slabs, collector counts,
distributed vs standalone, retention or the ServiceOps combined-server logic.
* Port `motadata-boq/static/js/oo_sizing.js` (ObserveOps slabs from 172.16.12.77:8082, ServiceOps, Vulnerability +
  Patch) and the ServiceOps tables from `hw_sizing.py` into `backend/app/modules/rfp/sizing_engine.py`.
* **Parity test:** run the JS (Node) and the Python over a few hundred input combinations; must give 0 differences
  before it is used.
* Admin can upload the sizing Excel (the same file `hw_sizing.parse_excel` reads) to update the ServiceOps tables,
  with versions. ObserveOps slabs: re-copy when the .77 page changes, or read them from .77 directly if .159 can reach it.
* The architecture agent extracts the named inputs (devices / monitors, interfaces, log GB/day or EPS, flows/sec, APM
  apps, retention days, technicians, assets, patch endpoints, HA, DC/DR) with RFP references.

### G5. Review screen: "Bid parameters" (new)
One tab in the workspace showing everything the outputs depend on, pre-filled from the RFP with references, all editable:
customer, products and modules, the sizing inputs from G4, licence type (perpetual / annual / SaaS), AMC years,
architecture (standalone / HA / DC-DR), support hours (8x5 / 24x7), onsite days, validity. Sizing results update live
as values change. **Confirm** locks the values and enables the bid pack.

### G6. Unpriced BOQ in the Motadata format
Recommended: **use the BOQ Generator (172.16.12.103:5050) as the single source** for SKUs, product wording and T&C.
* Add one API endpoint on 5050: bid parameters JSON in → unpriced SW BOQ `.xlsx` out (wraps
  `boq_generator.generate_boq_data` + `excel_builder`, which already supports unpriced). Admin edits in "BOQ Content"
  then flow into the presales platform with no copy.
* HW BOQ: built in the presales platform from the G4 sizing, in the same layout as the 5050 HW BOQ.
* Fallback if .159 cannot reach .103: copy the generator in and sync `content_data.json` on a schedule.
* Caution: the Python files on the 5050 server differ from the local copy; the endpoint must be added to the server
  version.

### G7. One-click bid pack
"Generate bid pack" (enabled after G5 Confirm) runs one job and gives a ZIP:
`Bid synopsis.docx`, `Scope matrix.xlsx`, `Pre-bid queries (tender format).xlsx/.docx`, `Compliance.xlsx`,
`HW sizing.xlsx`, `SW BOQ unpriced.xlsx`, `HW BOQ unpriced.xlsx`. Each file is also downloadable on its own; each
generation is versioned.

### G8. Chat about this RFP, with changes (done 2026-11-26: "Ask this RFP" panel)
* "Ask this RFP" side panel in the workspace. Context: the workspace's requirements (already embedded), extracted text
  segments, agent outputs, bid parameters, plus approved knowledge. Answers cite RFP pages.
* Change requests ("add a query on 3-year log retention", "make it DC + DR", "mark clause 7.3 partial") come back as
  proposed actions shown as a diff; on **Apply** they edit the agent output / parameters / answer and re-run only the
  affected outputs.

### G9. Knowledge: whole-site docs crawl and past experience
* Knowledge Hub "Add site": crawl a domain or path (sitemap first, then links), page limit, weekly re-sync, only
  changed pages re-indexed. Used for docs.motadata.com.
* If .159 has no internet: crawl from a machine that has, import as a ZIP.
* Bulk import of past compliance sheets (the importer exists) and past pre-bid query sheets (new).

### G10. Access from anywhere
Nginx already fronts the app on port 80. Add TLS (company certificate or Let's Encrypt), a DNS name, firewall NAT 443,
force HTTPS, secure cookies. Needs IT. Option: VPN only, with no firewall change.

## Order of work

| Step | Gaps | Why this order |
|---|---|---|
| 1 | G1, G3 | Pure prompt/schema/export changes in the RFP module; quick visible wins |
| 2 | G2 | One migration plus a prompt change; needs the Motadata profile text from you |
| 3 | G4 | Sizing port + parity test; needed by G5–G7 |
| 4 | G5, G6 | Parameters screen; BOQ endpoint on 5050 |
| 5 | G7 | Bid pack ties it together |
| 6 | G8 | Chat on top of everything above |
| 7 | G9, G10 | Knowledge crawl; HTTPS with IT (can start in parallel any time) |

Each step: tests added to `backend/tests`, `pytest` and `npx tsc --noEmit` clean, checked on a laptop copy with a real
RFP before it goes to `main`.

## Touches to shared code (agree with Naitik first)

Per `CONTRIBUTING.md`, these are shared foundations:
* `backend/alembic/versions`: new columns (G2), bid parameters table (G5), bid pack table (G7), pre-bid KB (G9).
* `backend/app/seed.py`: new agent keys `scope_summary`, `prebid_format`, `rfp_chat`, plus new Knowledge Hub sections.
* `backend/app/core/permissions.py`: `rfp.bidpack`, `rfp.chat`, `knowledge.crawl`.
* `frontend/src/components/ui.tsx`: only if a new shared component is needed (drag-reorder list).

Everything else stays inside the RFP and Knowledge Hub folders.

## Inputs needed

1. 3–5 past RFPs with the pre-bid queries and compliance sheets you actually submitted (used to check output quality).
2. Motadata profile text: modules, certifications, standard deviations and exclusions, partner scope.
3. Past pre-bid query sheets.
4. The sizing Excel and confirmation that 172.16.12.77:8082 is still the ObserveOps source.
5. From the .159 server: does it reach the internet, 172.16.12.103:5050 and 172.16.12.77:8082?
6. Who owns RFP Intelligence ("Teammate" in `CONTRIBUTING.md`), so changes go to the right person.
