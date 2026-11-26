"""Unpriced software BOQ from the Motadata BOQ Generator (172.16.12.103:5050), so SKU codes, product wording and
terms stay maintained in one place (its admin "BOQ Content" editor).

Signs in with a dedicated BOQ Generator account and calls its existing /api/download-boq with force_unpriced.
Settings, in backend/.env (read here so the shared app/config.py is unchanged):
  BOQ_GENERATOR_URL=http://172.16.12.103:5050
  BOQ_GENERATOR_USERNAME=<a BOQ Generator user, presales role recommended: it can never receive prices>
  BOQ_GENERATOR_PASSWORD=<its password>
"""
from __future__ import annotations

import io
import re

import httpx
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import BACKEND_DIR


class BoqSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")
    BOQ_GENERATOR_URL: str = "http://172.16.12.103:5050"
    BOQ_GENERATOR_USERNAME: str = ""
    BOQ_GENERATOR_PASSWORD: str = ""


class BoqError(Exception):
    pass


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


PRICE_WORDS = re.compile(r"price|amount|cost|total|rate|value", re.I)
HELPER_PRICE_COLUMNS = {"I", "J"}  # the BOQ template's unlabelled unit price and line total columns


def assert_unpriced(xlsx: bytes) -> None:
    """No pricing may ever leave this platform. Refuse the file if any sheet has a formula, or a number in a price
    column (a column headed price / amount / cost / total / rate / value near the top, or the template's I and J)."""
    wb = load_workbook(io.BytesIO(xlsx))
    for ws in wb.worksheets:
        price_cols: dict[str, int] = {c: 0 for c in HELPER_PRICE_COLUMNS}
        for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 6)):
            for c in row:
                col = get_column_letter(c.column)
                if isinstance(c.value, str) and PRICE_WORDS.search(c.value) and len(c.value) < 40 and col not in price_cols:
                    price_cols[col] = c.row
        for row in ws.iter_rows():
            for c in row:
                v, col = c.value, get_column_letter(c.column)
                if isinstance(v, str) and v.startswith("="):
                    raise BoqError(f"Refused: the BOQ Generator file has a formula ({ws.title}!{c.coordinate}), which "
                                   "may carry prices. Nothing was downloaded.")
                if (col in price_cols and c.row > price_cols[col]
                        and isinstance(v, (int, float)) and not isinstance(v, bool) and v != 0):
                    raise BoqError(f"Refused: the BOQ Generator file has a value in a price column "
                                   f"({ws.title}!{c.coordinate}). Nothing was downloaded.")


def unpriced_boq(body: dict, settings: BoqSettings | None = None, transport: httpx.BaseTransport | None = None) -> bytes:
    s = settings or BoqSettings()
    if not s.BOQ_GENERATOR_USERNAME or not s.BOQ_GENERATOR_PASSWORD:
        raise BoqError("The BOQ Generator account is not set up. Add BOQ_GENERATOR_USERNAME and BOQ_GENERATOR_PASSWORD "
                       "to backend/.env on the server.")
    base = s.BOQ_GENERATOR_URL.rstrip("/")
    try:
        with httpx.Client(base_url=base, timeout=60, follow_redirects=False, transport=transport) as c:
            r = c.post("/login", data={"username": s.BOQ_GENERATOR_USERNAME, "password": s.BOQ_GENERATOR_PASSWORD})
            if r.status_code not in (301, 302, 303) or "session" not in c.cookies:
                raise BoqError("The BOQ Generator rejected the sign-in. Check BOQ_GENERATOR_USERNAME and BOQ_GENERATOR_PASSWORD.")
            r = c.post("/api/download-boq", json=body)
    except httpx.HTTPError as e:
        raise BoqError(f"Cannot reach the BOQ Generator at {base}: {e.__class__.__name__}") from e
    if r.status_code == 200 and r.headers.get("content-type", "").startswith(XLSX):
        assert_unpriced(r.content)
        return r.content
    try:
        msg = r.json().get("error") or r.text[:300]
    except ValueError:
        msg = r.text[:300]
    raise BoqError(f"BOQ Generator: {msg}")
