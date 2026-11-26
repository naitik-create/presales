"""Past pre-bid query sheets (Excel, or a Word table) as reusable knowledge.

Each query becomes one entry (clause, query, suggested change, the authority's reply) in a Markdown document that is
stored as a normal Knowledge Hub source in "Internal presales knowledge", titled "Past pre-bid queries - <customer>".
The pre-bid query agent and the RFP chat find them like any other approved knowledge. Pure functions; the file is
read with app.parsing.extract.
"""
from __future__ import annotations

TITLE_PREFIX = "Past pre-bid queries - "
COLUMNS = {
    # field: header words, most specific first
    "query": ("clarification sought", "query / clarification", "queries", "query", "clarification required",
              "clarification", "bidder's query", "point of clarification"),
    "reply": ("reply", "response", "answer", "clarification by", "clarification given", "remarks of",
              "authority", "department", "purchaser", "tendering", "client"),
    "clause_text": ("existing clause", "clause text", "rfp clause", "content of rfp", "rfp text", "rfp content",
                    "clause details", "specification", "description", "existing"),
    "suggested_change": ("suggest", "proposed", "amendment", "requested change", "change requested", "modification"),
    "clause_no": ("clause no", "clause number", "clause ref", "section", "clause"),
    "page": ("page",),
    "sl_no": ("s.no", "s. no", "sl", "sr", "no.", "#"),
}
_ORDER = ["query", "reply", "suggested_change", "clause_text", "page", "clause_no", "sl_no"]


def _detect(lower: list[str]) -> dict[str, int] | None:
    cols: dict[str, int] = {}
    for field in _ORDER:
        for w in COLUMNS[field]:  # most specific words first
            i = next((i for i, h in enumerate(lower) if i not in cols.values() and h and w in h), None)
            if i is not None:
                cols[field] = i
                break
    # a header row names the query column and at least one other (a title row like "Pre-bid queries" does not)
    return cols if "query" in cols and len(cols) >= 2 else None


def parse_rows(rows: list[tuple[str, str, list[str]]]) -> tuple[list[dict], list[dict]]:
    """rows = [(sheet or table, ref, cells)]. Returns (queries, detected header per sheet {sheet, field: heading})."""
    queries, found = [], []
    sheet_now, cols, headers = None, None, []
    for sheet, ref, raw in rows:
        if sheet != sheet_now:
            sheet_now, cols = sheet, None
        cells = [str(c).strip() for c in raw]
        if cols is None:
            cols = _detect([c.lower() for c in cells])
            if cols:
                headers = cells
                found.append({"sheet": sheet, **{f: headers[i] for f, i in cols.items()}})
            continue
        q = {f: (cells[i] if i < len(cells) else "") for f, i in cols.items()}
        if len(q.get("query", "")) < 10:
            continue
        q["ref"] = ref
        queries.append(q)
    return queries, found


def to_markdown(meta: dict, queries: list[dict]) -> str:
    """One heading per query so each stays together when the document is split for search."""
    head = [f"# {TITLE_PREFIX}{meta.get('customer', '')}".strip(),
            f"Customer: {meta.get('customer', '')}. Tender: {meta.get('tender', '') or 'not given'}. "
            f"Date: {meta.get('date', '') or 'not given'}. Outcome of the bid: {meta.get('outcome', '') or 'not given'}.", ""]
    out = head
    for n, q in enumerate(queries, start=1):
        where = ", ".join(x for x in (f"clause {q['clause_no']}" if q.get("clause_no") else "",
                                      f"page {q['page']}" if q.get("page") else "") if x)
        out.append(f"## Query {n}{' (' + where + ')' if where else ''}")
        if q.get("clause_text"):
            out += [f"RFP clause: {q['clause_text']}", ""]
        out += [f"Query raised: {q['query']}", ""]
        if q.get("suggested_change"):
            out += [f"Change requested: {q['suggested_change']}", ""]
        out += [f"Authority's reply: {q.get('reply') or 'not recorded'}", ""]
    return "\n".join(out).strip() + "\n"
