"""Brand rules for exported documents (§18.4): black header rows with white text, Inter with Arial fallback, accent used sparingly."""
import io
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

BLACK = "000000"
WHITE = "FFFFFF"
OFF_WHITE = "F9F9F9"
BORDER = "E5E5E5"
MEDIUM_GRAY = "6B6B6B"
ACCENT = "F17463"
FONT = "Inter"

LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "logo.png"  # used only when no logo is uploaded in Administration


def _export_logo():
    from app.modules.branding.routes import export_logo_bytes
    data = export_logo_bytes()
    if data:
        return io.BytesIO(data)
    return str(LOGO_PATH) if LOGO_PATH.exists() else None


# ---------- Excel ----------
def new_workbook() -> Workbook:
    wb = Workbook()
    wb.remove(wb.active)
    return wb


def write_table(wb: Workbook, title: str, headers: list[str], rows: list[list], widths: list[int] | None = None,
                heading: str | None = None) -> None:
    ws = wb.create_sheet(title[:31])
    r0 = 1
    if heading:
        ws.cell(row=1, column=1, value=heading).font = Font(name=FONT, size=14, bold=True, color=BLACK)
        r0 = 3
    thin = Side(style="thin", color=BORDER)
    for j, h in enumerate(headers, start=1):
        c = ws.cell(row=r0, column=j, value=h)
        c.font = Font(name=FONT, bold=True, color=WHITE)
        c.fill = PatternFill("solid", fgColor=BLACK)
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for i, row in enumerate(rows, start=r0 + 1):
        for j, v in enumerate(row, start=1):
            c = ws.cell(row=i, column=j, value=v)
            c.font = Font(name=FONT, size=10, color=BLACK)
            c.alignment = Alignment(vertical="top", wrap_text=True)
            c.border = Border(bottom=thin)
    for j, w in enumerate(widths or [18] * len(headers), start=1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = ws.cell(row=r0 + 1, column=1)
    if rows:
        ws.auto_filter.ref = f"A{r0}:{get_column_letter(len(headers))}{r0 + len(rows)}"


def workbook_bytes(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------- Word ----------
def new_document(title: str, subtitle: str = "") -> Document:
    doc = Document()
    styles = doc.styles
    for name in ("Normal", "Heading 1", "Heading 2", "Heading 3", "Title"):
        st = styles[name]
        st.font.name = FONT  # Word falls back to Arial-like defaults when Inter is not installed
        st.font.color.rgb = RGBColor(0, 0, 0)
    styles["Normal"].font.size = Pt(10.5)
    logo = _export_logo()
    if logo is not None:
        doc.sections[0].header.paragraphs[0].add_run().add_picture(logo, width=Pt(110))
    t = doc.add_paragraph()
    run = t.add_run(title)
    run.font.size, run.font.bold = Pt(22), True
    if subtitle:
        s = doc.add_paragraph()
        r = s.add_run(subtitle)
        r.font.size, r.font.color.rgb = Pt(11), RGBColor(0x6B, 0x6B, 0x6B)
    return doc


def _shade(cell, hex_color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def add_table(doc: Document, headers: list[str], rows: list[list], widths_pt: list[int] | None = None) -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    for j, h in enumerate(headers):
        cell = table.rows[0].cells[j]
        cell.text = ""
        run = cell.paragraphs[0].add_run(h)
        run.font.bold, run.font.color.rgb, run.font.size = True, RGBColor(0xFF, 0xFF, 0xFF), Pt(9.5)
        _shade(cell, BLACK)
    for row in rows:
        cells = table.add_row().cells
        for j, v in enumerate(row):
            cells[j].text = ""
            cells[j].paragraphs[0].add_run("" if v is None else str(v)).font.size = Pt(9.5)
    if widths_pt:
        for row in table.rows:
            for j, w in enumerate(widths_pt):
                row.cells[j].width = Pt(w)
    doc.add_paragraph()


def document_bytes(doc: Document) -> bytes:
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
