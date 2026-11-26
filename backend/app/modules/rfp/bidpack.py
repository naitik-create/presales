"""Bid synopsis facts and pre-bid query formatting. Pure functions, no database or AI calls, so they are easy to test."""
from __future__ import annotations

NOT_STATED = "Not stated"

# (key, label) in the order the bid synopsis shows them.
BID_FACTS: list[tuple[str, str]] = [
    ("tender_number", "Tender / bid number"),
    ("issuing_authority", "Issuing authority / buyer"),
    ("bid_type", "Bid type and portal (GeM, e-procurement, manual)"),
    ("estimated_value", "Estimated contract value"),
    ("emd", "EMD / bid security"),
    ("tender_fee", "Tender fee"),
    ("pbg", "Performance bank guarantee"),
    ("contract_period", "Contract period"),
    ("warranty_amc", "Warranty, AMC / ATS period"),
    ("delivery_timeline", "Delivery and implementation timeline"),
    ("bidder_turnover", "Bidder turnover criterion"),
    ("bidder_experience", "Bidder experience criterion (similar projects)"),
    ("certifications", "Certifications required (bidder and OEM)"),
    ("oem_criteria", "OEM criteria (MAF, OEM turnover, presence, support centre)"),
    ("make_in_india", "Make in India / local content class"),
    ("consortium_subcontracting", "Consortium and subcontracting"),
    ("evaluation_method", "Evaluation method (L1, QCBS weights)"),
    ("payment_terms", "Payment terms"),
    ("sla_penalties", "SLA and penalties"),
    ("liquidated_damages", "Liquidated damages and caps"),
]

PREBID_CATEGORIES = [
    "Restrictive or vendor-specific specification", "Eligibility / PQ relaxation", "OEM / MAF condition",
    "Quantity or sizing unclear", "Scope unclear", "SLA / penalty", "Payment / commercial terms", "Timeline",
    "Contradiction", "Other",
]

# Fields a tender's pre-bid query columns can be mapped onto.
PREBID_FIELDS = ["sl_no", "document", "section", "page", "clause_no", "ref", "clause_text", "query",
                 "suggested_change", "reason", "blank"]

# Used when the RFP does not prescribe a format.
STANDARD_COLUMNS: list[dict] = [
    {"heading": "Sl. No.", "field": "sl_no"},
    {"heading": "RFP Document / Volume", "field": "document"},
    {"heading": "Section", "field": "section"},
    {"heading": "Page No.", "field": "page"},
    {"heading": "Clause No.", "field": "clause_no"},
    {"heading": "Existing Clause (as per RFP)", "field": "clause_text"},
    {"heading": "Clarification Sought", "field": "query"},
    {"heading": "Suggested Change", "field": "suggested_change"},
]

TOP_N = 10
_IMPACT = {"High": 0, "Medium": 1, "Low": 2}


def _empty(v) -> bool:
    return v is None or v == "" or v == [] or (isinstance(v, str) and v.strip().lower() == NOT_STATED.lower())


def merge_outputs(merged: dict, out: dict) -> dict:
    """Combine an agent's output for one window of a long RFP into the running result."""
    for k, v in out.items():
        cur = merged.get(k)
        if cur is None:
            merged[k] = v
        elif k == "tender_format":
            if not cur.get("found") and v.get("found"):
                merged[k] = v
        elif isinstance(v, list):
            merged[k] = list(cur) + list(v)
        elif isinstance(v, str):
            merged[k] = (cur + "\n\n" + v).strip() if cur else v
        elif isinstance(v, dict) and isinstance(cur, dict):
            merged[k] = _merge_facts(cur, v)
        else:
            merged[k] = v
    return merged


def _merge_facts(cur: dict, new: dict) -> dict:
    out = dict(cur)
    for k, v in new.items():
        if k not in out or (_empty((out[k] or {}).get("value")) and not _empty((v or {}).get("value"))):
            out[k] = v
    return out


def facts_list(facts) -> list[dict]:
    """The model returns bid_facts as an object; store it as an ordered, labelled list for display and export."""
    if isinstance(facts, list):
        return facts  # already converted
    facts = facts or {}
    rows = []
    for key, label in BID_FACTS:
        f = facts.get(key) or {}
        rows.append({"item": label, "value": f.get("value") or NOT_STATED, "ref": f.get("ref") or ""})
    return rows


def finalise_analysis(out: dict) -> dict:
    out["bid_facts"] = facts_list(out.get("bid_facts"))
    flags = out.get("red_flags") or []
    out["red_flags"] = sorted(flags, key=lambda x: _IMPACT.get(x.get("impact"), 3))
    return out


def finalise_prebid(out: dict) -> dict:
    """Order by rank (impact breaks ties), drop duplicates, renumber 1..n and pre-select the top 10."""
    seen, queries = set(), []
    for q in sorted(out.get("queries") or [], key=lambda q: (q.get("rank") or 999, _IMPACT.get(q.get("impact"), 3))):
        key = " ".join((q.get("query") or "").lower().split())
        if not key or key in seen:
            continue
        seen.add(key)
        queries.append(q)
    for i, q in enumerate(queries, start=1):
        q["rank"] = i
        q["selected"] = i <= TOP_N
    out["queries"] = queries
    out.setdefault("tender_format", {"found": False, "ref": "", "instructions": "", "columns": []})
    return out


def selected_queries(out: dict) -> list[dict]:
    """The queries to submit, in the order shown. Older runs have no selection: take the first ten."""
    qs = list(out.get("queries") or [])
    if any("selected" in q for q in qs):
        return [q for q in qs if q.get("selected")]
    return qs[:TOP_N]


def columns_for(out: dict) -> list[dict]:
    fmt = out.get("tender_format") or {}
    cols = [c for c in (fmt.get("columns") or []) if (c.get("heading") or "").strip()]
    return cols if fmt.get("found") and cols else STANDARD_COLUMNS


def _cell(q: dict, field: str, sl: int) -> str:
    if field == "sl_no":
        return str(sl)
    if field == "blank":
        return ""
    if field == "query":
        return q.get("query") or ""
    if field == "ref":
        return q.get("ref") or " ".join(x for x in (q.get("document"), q.get("page"), q.get("clause_no")) if x)
    if field == "clause_no" and not q.get("clause_no"):
        return q.get("ref") or ""  # older runs only have ref
    return q.get(field) or ""


def prebid_table(out: dict) -> tuple[list[str], list[list[str]]]:
    """Headers and rows for the selected queries, in the tender's own column format."""
    cols = columns_for(out)
    rows = [[_cell(q, c["field"], i) for c in cols] for i, q in enumerate(selected_queries(out), start=1)]
    return [c["heading"] for c in cols], rows
