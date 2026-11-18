"""Extract text with structure from uploaded files (§4.1, §6.2, §8.2).

Every extractor returns a list of Segment: a piece of text plus where it came from (page, sheet/row, section path).
"""
import csv
import io
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from app.config import get_settings


@dataclass
class Segment:
    text: str
    ref: str = ""  # "p.4", "Sheet1!R12", "para 33"
    section: str = ""  # heading path, e.g. "3 Scope > 3.2 Monitoring"
    file: str = ""
    cells: list[str] = field(default_factory=list)  # for spreadsheet rows


@dataclass
class Extracted:
    segments: list[Segment]
    used_ocr: bool = False
    page_count: int = 0


class ExtractionError(Exception):
    pass


def extract(data: bytes, name: str) -> Extracted:
    ext = Path(name).suffix.lower()
    if ext == ".pdf":
        return _pdf(data, name)
    if ext == ".docx":
        return _docx(data, name)
    if ext == ".xlsx":
        return _xlsx(data, name)
    if ext in (".doc", ".xls"):
        target = "docx" if ext == ".doc" else "xlsx"
        return extract(_libreoffice_convert(data, name, target), Path(name).stem + "." + target)
    if ext == ".csv":
        return _csv(data, name)
    if ext in (".txt", ".md"):
        return _text(data.decode("utf-8", errors="replace"), name, markdown=ext == ".md")
    if ext in (".html", ".htm"):
        return html_to_segments(data.decode("utf-8", errors="replace"), name)
    if ext == ".zip":
        return _zip(data, name)
    raise ExtractionError(f"Unsupported file type: {ext}")


def _pdf(data: bytes, name: str) -> Extracted:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    segs: list[Segment] = []
    blank_pages: list[int] = []
    for i, page in enumerate(reader.pages, start=1):
        txt = (page.extract_text() or "").strip()
        if len(txt) < 40:
            blank_pages.append(i)
        else:
            segs.append(Segment(text=txt, ref=f"p.{i}", file=name))
    used_ocr = False
    if blank_pages and ocr_available():
        for i, txt in _ocr_pages(data, blank_pages):
            if txt.strip():
                segs.append(Segment(text=txt.strip(), ref=f"p.{i} (OCR)", file=name))
                used_ocr = True
        segs.sort(key=lambda s: int(s.ref.split(".")[1].split()[0]))
    elif blank_pages and not segs:
        raise ExtractionError("This PDF has no text layer and OCR is not configured (set OCR_ENGINE_PATH).")
    return Extracted(segs, used_ocr, len(reader.pages))


def ocr_available() -> bool:
    p = get_settings().OCR_ENGINE_PATH
    return bool(p and Path(p).exists()) or shutil.which("tesseract") is not None


def _ocr_pages(data: bytes, pages: list[int]):
    import pypdfium2 as pdfium
    import pytesseract

    if get_settings().OCR_ENGINE_PATH:
        pytesseract.pytesseract.tesseract_cmd = get_settings().OCR_ENGINE_PATH
    pdf = pdfium.PdfDocument(data)
    for i in pages:
        img = pdf[i - 1].render(scale=300 / 72).to_pil()
        yield i, pytesseract.image_to_string(img, lang="eng")


def _docx(data: bytes, name: str) -> Extracted:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    d = docx.Document(io.BytesIO(data))
    segs: list[Segment] = []
    path: list[tuple[int, str]] = []
    para_no = 0
    for block in d.element.body.iterchildren():
        tag = block.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(block, d)
            txt = p.text.strip()
            if not txt:
                continue
            para_no += 1
            style = (p.style.name or "") if p.style is not None else ""
            if style.lower().startswith("heading"):
                try:
                    level = int(style.split()[-1])
                except ValueError:
                    level = 1
                path = [x for x in path if x[0] < level] + [(level, txt)]
                continue
            segs.append(Segment(text=txt, ref=f"para {para_no}", section=" > ".join(h for _, h in path), file=name))
        elif tag == "tbl":
            t = Table(block, d)
            for r_i, row in enumerate(t.rows, start=1):
                cells = [c.text.strip() for c in row.cells]
                cells = [c for j, c in enumerate(cells) if c and (j == 0 or c != cells[j - 1])]  # merged cells repeat
                if cells:
                    segs.append(Segment(text=" | ".join(cells), ref=f"table row {r_i}",
                                        section=" > ".join(h for _, h in path), file=name, cells=cells))
    return Extracted(segs, False, 0)


def _xlsx(data: bytes, name: str) -> Extracted:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    segs: list[Segment] = []
    for ws in wb.worksheets:
        for r_i, row in enumerate(ws.iter_rows(values_only=True), start=1):
            cells = ["" if v is None else str(v).strip() for v in row]
            while cells and not cells[-1]:
                cells.pop()
            if any(cells):
                segs.append(Segment(text=" | ".join(c for c in cells if c), ref=f"{ws.title}!R{r_i}",
                                    section=ws.title, file=name, cells=cells))
    return Extracted(segs, False, len(wb.worksheets))


def _csv(data: bytes, name: str) -> Extracted:
    text = data.decode("utf-8-sig", errors="replace")
    segs = []
    for r_i, row in enumerate(csv.reader(io.StringIO(text)), start=1):
        cells = [c.strip() for c in row]
        if any(cells):
            segs.append(Segment(text=" | ".join(c for c in cells if c), ref=f"R{r_i}", file=name, cells=cells))
    return Extracted(segs, False, 0)


def _text(text: str, name: str, markdown: bool = False) -> Extracted:
    segs: list[Segment] = []
    path: list[tuple[int, str]] = []
    buf: list[str] = []
    start_line = 1

    def flush(line_no: int):
        nonlocal buf, start_line
        if "".join(buf).strip():
            segs.append(Segment(text="\n".join(buf).strip(), ref=f"line {start_line}",
                                section=" > ".join(h for _, h in path), file=name))
        buf, start_line = [], line_no

    for n, line in enumerate(text.splitlines(), start=1):
        if markdown and line.startswith("#"):
            flush(n + 1)
            level = len(line) - len(line.lstrip("#"))
            path = [x for x in path if x[0] < level] + [(level, line.lstrip("# ").strip())]
        elif not line.strip():
            flush(n + 1)
        else:
            buf.append(line)
    flush(0)
    return Extracted(segs, False, 0)


def html_to_segments(html: str, name: str) -> Extracted:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "nav", "footer", "header", "noscript", "form"]):
        t.decompose()
    segs: list[Segment] = []
    path: list[tuple[int, str]] = []
    body = soup.find("main") or soup.find("article") or soup.body or soup
    for el in body.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "pre"]):
        txt = el.get_text(" ", strip=True)
        if not txt:
            continue
        if el.name in ("h1", "h2", "h3", "h4"):
            level = int(el.name[1])
            path = [x for x in path if x[0] < level] + [(level, txt)]
            continue
        segs.append(Segment(text=txt, ref="", section=" > ".join(h for _, h in path), file=name))
    return Extracted(segs, False, 0)


def _zip(data: bytes, name: str) -> Extracted:
    out: list[Segment] = []
    used_ocr = False
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            if info.is_dir() or info.file_size > 200 * 1024 * 1024:
                continue
            inner = Path(info.filename).name
            if Path(inner).suffix.lower() not in {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv", ".txt", ".md"}:
                continue
            ex = extract(z.read(info), inner)
            used_ocr |= ex.used_ocr
            out.extend(ex.segments)
    return Extracted(out, used_ocr, 0)


def libreoffice_path() -> str | None:
    p = get_settings().LIBREOFFICE_PATH
    if p and Path(p).exists():
        return p
    return shutil.which("soffice")


def _libreoffice_convert(data: bytes, name: str, target: str) -> bytes:
    exe = libreoffice_path()
    if not exe:
        raise ExtractionError("Legacy .doc/.xls files need LibreOffice. Set LIBREOFFICE_PATH.")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / Path(name).name
        src.write_bytes(data)
        subprocess.run([exe, "--headless", "--convert-to", target, "--outdir", tmp, str(src)],
                       check=True, timeout=180, capture_output=True)
        out = src.with_suffix("." + target)
        if not out.exists():
            raise ExtractionError(f"LibreOffice could not convert {name}")
        return out.read_bytes()


def docx_to_pdf(docx_bytes: bytes) -> bytes:
    exe = libreoffice_path()
    if not exe:
        raise ExtractionError("PDF export needs LibreOffice. Set LIBREOFFICE_PATH.")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "document.docx"
        src.write_bytes(docx_bytes)
        subprocess.run([exe, "--headless", "--convert-to", "pdf", "--outdir", tmp, str(src)],
                       check=True, timeout=180, capture_output=True)
        return (Path(tmp) / "document.pdf").read_bytes()
