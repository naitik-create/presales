import io

from app.exports import brand
from app.modules.rfp import bidpack
from app.modules.rfp.agents import DOC_AGENT_LABELS


def compliance_sheet(ws_name: str, rows: list[tuple]) -> bytes:
    wb = brand.new_workbook()
    brand.write_table(wb, "Compliance", ["No.", "Requirement", "Reference", "Category", "Compliance", "Response", "Remarks"],
                      [[r.number, r.text, f"{r.source_file} {r.source_ref}".strip(), r.category,
                        c.status if c else "", c.response if c else "", ""] for r, c in rows],
                      [8, 70, 26, 14, 22, 70, 30], heading=f"Compliance statement - {ws_name}")
    return brand.workbook_bytes(wb)


def internal_workbook(ws_name: str, rows: list[tuple], runs: dict) -> bytes:
    wb = brand.new_workbook()
    brand.write_table(wb, "Compliance (internal)", ["No.", "Requirement", "Reference", "Status", "Response", "Explanation",
                                                    "Evidence", "Sources", "Validation remarks", "Origin", "Approved", "Change"],
                      [[r.number, r.text, f"{r.source_file} {r.source_ref}".strip(), c.status if c else "",
                        c.response if c else "", c.explanation if c else "", c.evidence if c else "",
                        "; ".join(_cite(s) for s in (c.sources if c else [])), c.validation_remarks if c else "",
                        c.origin if c else "", "Yes" if c and c.approved else "No", r.change] for r, c in rows],
                      [8, 60, 22, 20, 50, 40, 40, 40, 36, 14, 10, 10], heading=f"RFP workspace - {ws_name}")
    if "risk" in runs:
        brand.write_table(wb, "Risks", ["Category", "Description", "Impact", "Reference", "Mitigation"],
                          [[i["category"], i["description"], i["impact"], i["ref"], i["mitigation"]] for i in runs["risk"].get("items", [])],
                          [22, 60, 10, 20, 50])
    if "scope" in runs:
        brand.write_table(wb, "Scope", SCOPE_HEADERS, _scope_rows(rows, runs["scope"]), SCOPE_WIDTHS)
    if "analysis" in runs:
        brand.write_table(wb, "Bid synopsis", ["Item", "Value", "Reference"],
                          [[f["item"], f["value"], f["ref"]] for f in bidpack.facts_list(runs["analysis"].get("bid_facts"))],
                          [36, 70, 22])
    if "prebid" in runs:
        brand.write_table(wb, "Pre-bid queries", ["Rank", "Submit", "Impact", "Category", "Reference", "Clause", "Query",
                                                  "Suggested change", "Reason (internal)"],
                          [[q.get("rank", ""), "Yes" if q in bidpack.selected_queries(runs["prebid"]) else "",
                            q.get("impact", ""), q.get("category", ""), q.get("ref", ""), q.get("clause_text", ""),
                            q.get("query", ""), q.get("suggested_change", ""), q.get("reason", "")]
                           for q in runs["prebid"].get("queries", [])],
                          [7, 8, 9, 24, 20, 50, 60, 40, 40])
    if "boq" in runs:
        brand.write_table(wb, "BOQ inputs", ["Product", "Module", "Licence metric", "Quantity", "Assumption", "Reference"],
                          [[x["product"], x["module"], x["licence_metric"], x["quantity"], x["assumption"], x["ref"]]
                           for x in runs["boq"].get("lines", [])], [16, 26, 22, 12, 40, 20])
    if "pqtq" in runs:
        brand.write_table(wb, "PQ-TQ drafts", ["Type", "Criterion", "Reference", "Draft response", "Evidence", "Missing items"],
                          [[x["type"], x["criterion"], x["ref"], x["draft_response"], x["supporting_evidence"], "; ".join(x["missing_items"])]
                           for x in runs["pqtq"].get("items", [])], [8, 50, 18, 50, 36, 36])
    return brand.workbook_bytes(wb)


def _cite(s: dict) -> str:
    if s.get("kind") == "submitted_rfp":
        return f"Past RFP {s.get('customer')} {s.get('submitted_on')} v{s.get('product_version')}"
    return f"{s.get('title', '')} {s.get('page', '')}".strip()


def _scope_rows(rows: list[tuple], scope: dict) -> list[list]:
    by_no = {m["number"]: m for m in scope.get("matrix", [])}
    out = []
    for r, c in rows:
        m = by_no.get(r.number, {})
        out.append([r.number, r.text, f"{r.source_file} {r.source_ref}".strip(), r.category, m.get("owner", ""),
                    m.get("product", ""), m.get("module", ""), c.status if c else "", m.get("note", "")])
    return out


SCOPE_HEADERS = ["No.", "Requirement", "Reference", "Category", "Owner", "Product", "Module", "Compliance", "Note"]
SCOPE_WIDTHS = [8, 70, 22, 14, 14, 13, 30, 22, 36]


def scope_workbook(ws_name: str, rows: list[tuple], scope: dict) -> bytes:
    wb = brand.new_workbook()
    brand.write_table(wb, "Scope matrix", SCOPE_HEADERS, _scope_rows(rows, scope), SCOPE_WIDTHS,
                      heading=f"Motadata scope - {ws_name}")
    brand.write_table(wb, "Modules in scope", ["Product", "Module", "Basis"],
                      [[m["product"], m["module"], m["basis"]] for m in scope.get("modules_in_scope", [])], [14, 40, 60])
    summary = []
    for key, label in (("partner_items", "Partner / SI"), ("customer_prerequisites", "Customer prerequisite"),
                       ("out_of_scope", "Out of scope"), ("motadata_gaps", "Motadata gap")):
        summary += [[label, it["item"], it.get("ref", ""), it.get("note", "")] for it in scope.get(key, [])]
    brand.write_table(wb, "Scope summary", ["Type", "Item", "Reference", "Note"], summary, [22, 70, 22, 40])
    return brand.workbook_bytes(wb)


HW_HEADERS = ["Site", "Component", "Qty", "vCPU", "RAM (GB)", "Disk (GB)"]


def hw_rows(sizing: dict) -> list[list]:
    return [[site["title"], r["n"], r["q"], r["c"], r["r"], r["k"]] for site in sizing.get("sites", []) for r in site["rows"]]


def hw_sizing_workbook(ws_name: str, sizing: dict) -> bytes:
    wb = brand.new_workbook()
    brand.write_table(wb, "Hardware sizing", HW_HEADERS, hw_rows(sizing), [36, 50, 7, 8, 10, 11],
                      heading=f"Hardware sizing - {ws_name}")
    brand.write_table(wb, "Sizing inputs", ["Input", "Value", "RFP reference", "Note"],
                      [[i["label"], i["value"], i["ref"], i["note"]] for i in sizing.get("inputs", [])], [50, 12, 26, 60])
    notes = [["Architecture", sizing.get("architecture", "")], ["ObserveOps topology", sizing.get("topology", "")],
             ["Retention", sizing.get("retention", "")], ["Status", sizing.get("status", "")]]
    if sizing.get("error"):
        notes.append(["Error", sizing["error"]])
    notes += [["Note", n] for n in sizing.get("notes", [])]
    notes.append(["Source", "Motadata sizing rules (ObserveOps sizing page, ServiceOps sizing tables, docs.motadata.com)"])
    brand.write_table(wb, "Notes", ["Item", "Detail"], notes, [22, 110])
    return brand.workbook_bytes(wb)


ARCH_LABEL = {"standalone": "Standalone", "ha": "High availability (HA)", "dr": "Disaster recovery (DR)",
              "dc_dr": "DC + DR", "ha_dr": "HA + DR"}


def hw_boq_workbook(ws_name: str, params: dict, sizing: dict) -> bytes:
    """Unpriced hardware BOQ: one line per server per site, specification in words, quantity; no prices."""
    rows, sr = [], 0
    for site in sizing.get("sites", []):
        rows.append(["", site["title"], "", ""])
        for r in site["rows"]:
            sr += 1
            rows.append([sr, r["n"], f"{r['c']} vCPU, {r['r']} GB RAM, {r['k']} GB usable disk", r["q"]])
    wb = brand.new_workbook()
    brand.write_table(wb, "HW BOQ (unpriced)", ["Sr. No.", "Item", "Minimum specification", "Qty"], rows, [8, 50, 52, 7],
                      heading=f"Hardware BOQ (unpriced) - {params.get('customer_name') or ws_name}")
    terms = [
        ["Architecture", ARCH_LABEL.get(params.get("architecture"), params.get("architecture", ""))],
        ["ObserveOps topology", sizing.get("topology", "")],
        ["Retention", sizing.get("retention", "")],
        ["Servers", "Physical or virtual. Specifications are the minimum per server; storage is usable capacity "
                    "after RAID, on SSD for ObserveOps data."],
        ["Not included", "Operating system and database licences, racks, network and backup equipment are supplied "
                         "by the partner or customer as per the RFP."],
        ["Source", "Motadata sizing rules (ObserveOps sizing page, ServiceOps sizing tables, docs.motadata.com)"],
    ] + [["Note", n] for n in sizing.get("notes", [])]
    brand.write_table(wb, "Notes", ["Item", "Detail"], terms, [22, 110])
    return brand.workbook_bytes(wb)


def bid_pack(ws_name: str, rows: list[tuple], runs: dict, bp: dict, sw_boq) -> tuple[bytes, list[dict]]:
    """All bid outputs in one ZIP. sw_boq() returns the unpriced SW BOQ bytes or raises; a failed part is listed in
    the manifest and README instead of stopping the pack. Returns (zip bytes, manifest)."""
    import zipfile
    from datetime import datetime

    p, sizing = bp["params"], bp["sizing"]
    who = p.get("customer_name") or ws_name
    parts: list[tuple[str, object]] = [
        ("01 Bid synopsis and RFP analysis.docx", lambda: report_docx(ws_name, runs)),
        ("02 Motadata scope matrix.xlsx", (lambda: scope_workbook(ws_name, rows, runs["scope"])) if runs.get("scope")
         else "Motadata scope has not been run"),
        ("03 Pre-bid queries (tender format).xlsx", (lambda: prebid_sheet(ws_name, runs["prebid"]))
         if (runs.get("prebid") or {}).get("queries") else "Pre-bid queries have not been run"),
        ("03 Pre-bid queries (tender format).docx", (lambda: prebid_docx(ws_name, runs["prebid"]))
         if (runs.get("prebid") or {}).get("queries") else "Pre-bid queries have not been run"),
        ("04 Compliance statement.xlsx", (lambda: compliance_sheet(ws_name, rows)) if rows else "No requirements yet"),
        ("05 Hardware sizing.xlsx", (lambda: hw_sizing_workbook(ws_name, sizing)) if sizing.get("sites")
         else sizing.get("error") or "No hardware sizing"),
        ("06 Unpriced HW BOQ.xlsx", (lambda: hw_boq_workbook(ws_name, p, sizing)) if sizing.get("sites")
         else sizing.get("error") or "No hardware sizing"),
        ("07 Unpriced SW BOQ.xlsx", sw_boq),
        ("Internal/RFP workspace (internal).xlsx", lambda: internal_workbook(ws_name, rows, runs)),
    ]
    manifest: list[dict] = []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, make in parts:
            if isinstance(make, str):
                manifest.append({"name": name, "included": False, "note": make})
                continue
            try:
                z.writestr(name, make())
                manifest.append({"name": name, "included": True, "note": ""})
            except Exception as e:  # one failed part must not lose the rest of the pack
                manifest.append({"name": name, "included": False, "note": str(e)[:300] or e.__class__.__name__})
        lines = [f"Bid pack - {who}", f"Workspace: {ws_name}", f"Generated: {datetime.now():%d %b %Y %H:%M}", "",
                 "No prices are included in this pack.", "", "Files:"]
        lines += [f"  [{'x' if m['included'] else ' '}] {m['name']}" + (f"  - not included: {m['note']}" if not m["included"] else "")
                  for m in manifest]
        lines += ["", "Confirmed bid parameters:"]
        lines += [f"  {k}: {v}" for k, v in p.items()]
        z.writestr("README.txt", "\n".join(lines) + "\n")
    return buf.getvalue(), manifest


def prebid_sheet(ws_name: str, prebid: dict) -> bytes:
    """The queries to submit, in the column format the RFP prescribes (or the standard format)."""
    headers, rows = bidpack.prebid_table(prebid)
    wb = brand.new_workbook()
    widths = [8 if h.lower().startswith(("sl", "s.", "sr", "no")) else 45 if len(h) > 12 else 18 for h in headers]
    brand.write_table(wb, "Pre-bid queries", headers, rows, widths, heading=f"Pre-bid queries - {ws_name}")
    return brand.workbook_bytes(wb)


def prebid_docx(ws_name: str, prebid: dict) -> bytes:
    headers, rows = bidpack.prebid_table(prebid)
    doc = brand.new_document(f"Pre-bid queries - {ws_name}")
    fmt = prebid.get("tender_format") or {}
    if fmt.get("found") and fmt.get("instructions"):
        doc.add_paragraph(f"Submission: {fmt['instructions']}")
    _landscape(doc)
    brand.add_table(doc, headers, rows)
    return brand.document_bytes(doc)


def _landscape(doc) -> None:
    from docx.enum.section import WD_ORIENT
    s = doc.sections[0]
    if s.orientation != WD_ORIENT.LANDSCAPE:
        s.orientation = WD_ORIENT.LANDSCAPE
        s.page_width, s.page_height = s.page_height, s.page_width


def _bid_synopsis(doc, analysis: dict) -> None:
    doc.add_heading("Bid synopsis", level=1)
    brand.add_table(doc, ["Item", "Value", "Reference"],
                    [[f["item"], f["value"], f["ref"]] for f in bidpack.facts_list(analysis.get("bid_facts"))])
    if analysis.get("dates"):
        doc.add_heading("Key dates", level=3)
        brand.add_table(doc, ["Item", "Date", "Reference"], [[d["item"], d["date"], d["ref"]] for d in analysis["dates"]])
    if analysis.get("red_flags"):
        doc.add_heading("Red flags", level=3)
        brand.add_table(doc, ["Issue", "Impact", "Reference"],
                        [[f["issue"], f["impact"], f["ref"]] for f in analysis["red_flags"]])


def report_docx(ws_name: str, runs: dict) -> bytes:
    doc = brand.new_document(f"RFP analysis - {ws_name}")
    if runs.get("analysis", {}).get("bid_facts"):
        _bid_synopsis(doc, runs["analysis"])
    for key in ("synopsis", "analysis", "scope", "architecture", "risk", "pqtq", "boq", "prebid"):
        out = runs.get(key)
        if not out:
            continue
        doc.add_heading(DOC_AGENT_LABELS[key], level=1)
        if key == "scope":  # the full matrix is in the scope workbook; the report shows the summary
            out = {k: v for k, v in out.items() if k != "matrix"}
        if key == "architecture":
            hw = out.get("motadata_sizing")
            out = {k: v for k, v in out.items() if k not in ("motadata_sizing", "motadata_inputs")}
            if hw and hw.get("sites"):
                doc.add_heading("Hardware sizing", level=3)
                brand.add_table(doc, HW_HEADERS, hw_rows(hw))
                for n in hw.get("notes", []):
                    doc.add_paragraph(n, style="List Bullet")
            elif hw and hw.get("error"):
                doc.add_paragraph(f"Hardware sizing: {hw['error']}")
        if key == "prebid":
            brand.add_table(doc, ["Rank", "Submit", "Impact", "Reference", "Query"],
                            [[q.get("rank", ""), "Yes" if q in bidpack.selected_queries(out) else "", q.get("impact", ""),
                              q.get("ref", ""), q.get("query", "")] for q in out.get("queries", [])])
            continue
        for k, v in out.items():
            if k in ("source_ids", "citations", "bid_facts", "red_flags"):
                continue
            label = k.replace("_", " ").capitalize()
            if isinstance(v, str) and v:
                doc.add_heading(label, level=3)
                doc.add_paragraph(v)
            elif isinstance(v, list) and v:
                doc.add_heading(label, level=3)
                if isinstance(v[0], dict):
                    headers = list(v[0].keys())
                    brand.add_table(doc, [h.replace("_", " ").capitalize() for h in headers],
                                    [[_flat(item.get(h)) for h in headers] for item in v])
                else:
                    for item in v:
                        doc.add_paragraph(str(item), style="List Bullet")
    return brand.document_bytes(doc)


def _flat(v) -> str:
    if isinstance(v, list):
        return "; ".join(_flat(x) for x in v)
    if isinstance(v, dict):
        return ", ".join(f"{k}: {_flat(x)}" for k, x in v.items())
    return "" if v is None else str(v)
