from app.exports import brand
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
    if "prebid" in runs:
        brand.write_table(wb, "Pre-bid queries", ["Reference", "Clause", "Query", "Reason"],
                          [[q["ref"], q["clause_text"], q["query"], q["reason"]] for q in runs["prebid"].get("queries", [])],
                          [20, 50, 60, 40])
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


def report_docx(ws_name: str, runs: dict) -> bytes:
    doc = brand.new_document(f"RFP analysis - {ws_name}")
    for key in ("synopsis", "analysis", "architecture", "risk", "pqtq", "boq", "prebid"):
        out = runs.get(key)
        if not out:
            continue
        doc.add_heading(DOC_AGENT_LABELS[key], level=1)
        for k, v in out.items():
            if k in ("source_ids", "citations"):
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
