"""Read a submitted compliance sheet (XLSX/XLS/CSV, or a Word table) into requirement-response pairs (§6.4)."""
from app.parsing.extract import extract

REQ_HEADERS = ("requirement", "specification", "description", "clause", "technical spec", "feature", "parameter")
STATUS_HEADERS = ("compliance", "complied", "status", "compliant", "yes/no", "y/n")
RESP_HEADERS = ("remark", "response", "comment", "explanation", "bidder", "vendor response", "justification")
REF_HEADERS = ("s.no", "sr", "sl", "no.", "ref", "clause no", "id", "#")


def _find(headers: list[str], names: tuple[str, ...], exclude: set[int]) -> int | None:
    for i, h in enumerate(headers):
        if i not in exclude and any(n in h for n in names):
            return i
    return None


def parse_rows(rows: list[tuple[str, str, list[str]]]) -> tuple[list[dict], list[dict]]:
    """rows = [(sheet or table, ref, cells)]. Returns (pairs, the header row found in each sheet:
    [{"sheet", "requirement", "status", "response", "ref"} with the heading text of each detected column])."""
    pairs: list[dict] = []
    found: list[dict] = []
    current_sheet = None
    cols: dict[str, int | None] | None = None
    for sheet, ref, raw in rows:
        if sheet != current_sheet:
            current_sheet, cols = sheet, None
        cells = [c.strip() for c in raw]
        lower = [c.lower() for c in cells]
        if cols is None:
            req = _find(lower, REQ_HEADERS, set())
            st = _find(lower, STATUS_HEADERS, {req} if req is not None else set())
            if req is not None and st is not None:
                used = {req, st}
                resp = _find(lower, RESP_HEADERS, used)
                ref_i = _find(lower, REF_HEADERS, used | ({resp} if resp is not None else set()))
                cols = {"req": req, "status": st, "resp": resp, "ref": ref_i}
                found.append({"sheet": sheet, **{k: (cells[i] if i is not None else "") for k, i in
                                                 (("requirement", req), ("status", st), ("response", resp), ("ref", ref_i))}})
            continue

        def cell(k: str) -> str:
            i = cols.get(k)
            return cells[i] if i is not None and i < len(cells) else ""

        requirement = cell("req")
        if len(requirement) < 8:
            continue
        pairs.append({"requirement": requirement, "status": cell("status"), "response": cell("resp"),
                      "reference": f"{ref} {cell('ref')}".strip()})
    return pairs, found


def _rows(data: bytes, name: str) -> list[tuple[str, str, list[str]]]:
    return [(seg.section, seg.ref, list(seg.cells)) for seg in extract(data, name).segments]


def parse_compliance_sheet(data: bytes, name: str) -> list[dict]:
    return parse_rows(_rows(data, name))[0]


def preview_compliance_sheet(data: bytes, name: str) -> dict:
    """What an import would read: the detected columns per sheet, the number of pairs and a sample."""
    pairs, headers = parse_rows(_rows(data, name))
    return {"columns": headers, "pairs": len(pairs), "sample": pairs[:5]}
