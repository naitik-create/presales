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
