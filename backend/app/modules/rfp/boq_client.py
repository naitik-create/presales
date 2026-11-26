"""Unpriced software BOQ from the Motadata BOQ Generator (172.16.12.103:5050), so SKU codes, product wording and
terms stay maintained in one place (its admin "BOQ Content" editor).

Signs in with a dedicated BOQ Generator account and calls its existing /api/download-boq with force_unpriced.
Settings, in backend/.env (read here so the shared app/config.py is unchanged):
  BOQ_GENERATOR_URL=http://172.16.12.103:5050
  BOQ_GENERATOR_USERNAME=<a BOQ Generator user, presales role recommended: it can never receive prices>
  BOQ_GENERATOR_PASSWORD=<its password>
"""
from __future__ import annotations

import httpx
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
        return r.content
    try:
        msg = r.json().get("error") or r.text[:300]
    except ValueError:
        msg = r.text[:300]
    raise BoqError(f"BOQ Generator: {msg}")
