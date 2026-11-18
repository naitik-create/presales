"""Placeholder-based Word templates (§8.6). Placeholders are written {{name}} in the template; branding is kept."""
import copy
import io
import re

from docx import Document

PH = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def _paragraphs(doc):
    yield from doc.paragraphs
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                yield from cell.paragraphs
    for s in doc.sections:
        for part in (s.header, s.footer):
            yield from part.paragraphs


def find_placeholders(data: bytes) -> list[str]:
    doc = Document(io.BytesIO(data))
    seen: list[str] = []
    for p in _paragraphs(doc):
        for name in PH.findall(p.text):
            if name not in seen:
                seen.append(name)
    return seen


def fill(data: bytes, values: dict[str, str]) -> bytes:
    doc = Document(io.BytesIO(data))
    for p in list(_paragraphs(doc)):
        text = p.text
        if not PH.search(text):
            continue
        whole = PH.fullmatch(text.strip())
        if whole and "\n" in values.get(whole.group(1), ""):
            _replace_with_paragraphs(p, values.get(whole.group(1), ""))
            continue
        new = PH.sub(lambda m: values.get(m.group(1), ""), text)
        runs = p.runs
        if runs:
            runs[0].text = new
            for r in runs[1:]:
                r.text = ""
        else:
            p.add_run(new)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _replace_with_paragraphs(p, content: str) -> None:
    """Replace a placeholder-only paragraph with one paragraph per line; '- ' lines become bullets when the style exists."""
    lines = [ln for ln in content.split("\n")]
    styles = {s.name for s in p.part.document.styles} if hasattr(p.part, "document") else set()
    anchor = p
    first = True
    for line in lines:
        if first:
            target = p
            for r in target.runs[1:]:
                r.text = ""
            if not target.runs:
                target.add_run("")
            first = False
        else:
            new_el = copy.deepcopy(p._p)
            anchor._p.addnext(new_el)
            from docx.text.paragraph import Paragraph
            target = Paragraph(new_el, p._parent)
            for r in target.runs[1:]:
                r.text = ""
        bullet = line.lstrip().startswith("- ")
        target.runs[0].text = line.lstrip()[2:] if bullet else line
        if bullet and "List Bullet" in styles:
            target.style = "List Bullet"
        anchor = target
