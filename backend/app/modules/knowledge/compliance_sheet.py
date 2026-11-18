"""Read a submitted compliance sheet (XLSX/XLS/CSV) into requirement-response pairs (§6.4)."""
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


def parse_compliance_sheet(data: bytes, name: str) -> list[dict]:
    ex = extract(data, name)
    pairs: list[dict] = []
    current_sheet = None
    cols: dict[str, int | None] | None = None
    for seg in ex.segments:
        if seg.section != current_sheet:
            current_sheet, cols = seg.section, None
        cells = [c.strip() for c in seg.cells]
        lower = [c.lower() for c in cells]
        if cols is None:
            req = _find(lower, REQ_HEADERS, set())
            st = _find(lower, STATUS_HEADERS, {req} if req is not None else set())
            if req is not None and st is not None:
                used = {req, st}
                resp = _find(lower, RESP_HEADERS, used)
                ref = _find(lower, REF_HEADERS, used | ({resp} if resp is not None else set()))
                cols = {"req": req, "status": st, "resp": resp, "ref": ref}
            continue

        def cell(k: str) -> str:
            i = cols.get(k)
            return cells[i] if i is not None and i < len(cells) else ""

        requirement = cell("req")
        if len(requirement) < 8:
            continue
        pairs.append({"requirement": requirement, "status": cell("status"), "response": cell("resp"),
                      "reference": f"{seg.ref} {cell('ref')}".strip()})
    return pairs
