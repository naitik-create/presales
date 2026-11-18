"""Logo uploads (§18.4). Logos are public assets because the sign-in page shows them before anyone signs in."""
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.deps import CurrentUser, require
from app.core.settings_store import get_setting, set_setting
from app.core.storage import read_file, save_file
from app.db import get_db
from app.models.core import StoredFile

public = APIRouter(prefix="/branding", tags=["branding"])
admin = APIRouter(prefix="/admin/branding", tags=["branding"])

KINDS = {
    "logo": {"label": "Full logo (light backgrounds)", "types": {".svg", ".png", ".jpg", ".jpeg"}, "placeholder": "/brand/logo-light.svg",
             "use": "Expanded sidebar and sign-in screen. Minimum width on screen is 120px."},
    "logomark": {"label": "Logomark (icon only)", "types": {".svg", ".png", ".jpg", ".jpeg"}, "placeholder": "/brand/logomark.svg",
                 "use": "Collapsed sidebar and browser tab icon."},
    "export": {"label": "Logo for Word documents", "types": {".png", ".jpg", ".jpeg"}, "placeholder": "",
               "use": "Header of exported Word and PDF documents. PNG or JPG, because Word cannot embed SVG."},
}
MAX_BYTES = 2 * 1024 * 1024
MIME = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
UNSAFE_SVG = re.compile(rb"<script|\bon[a-z]+\s*=|javascript:|<foreignObject|<iframe|<embed|<object", re.I)


def _branding(db: Session) -> dict:
    return get_setting(db, "branding") or {}


def _check(kind: str, name: str, data: bytes) -> str:
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in KINDS[kind]["types"]:
        raise HTTPException(400, f"{KINDS[kind]['label']} must be one of: {', '.join(sorted(KINDS[kind]['types']))}")
    if len(data) > MAX_BYTES:
        raise HTTPException(400, "Logo files must be 2 MB or smaller")
    if ext == ".png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(400, "This is not a valid PNG file")
    if ext in (".jpg", ".jpeg") and not data.startswith(b"\xff\xd8"):
        raise HTTPException(400, "This is not a valid JPEG file")
    if ext == ".svg":
        head = data[:500].lstrip().lower()
        if not (head.startswith(b"<svg") or head.startswith(b"<?xml")) or b"<svg" not in data[:4000].lower():
            raise HTTPException(400, "This is not a valid SVG file")
        if UNSAFE_SVG.search(data):
            raise HTTPException(400, "SVG files with scripts, event handlers or embedded content are not allowed")
    return ext


@public.get("")
def branding_info(db: Session = Depends(get_db)):
    b = _branding(db)
    return {k: {"set": k in b, "url": f"/api/branding/{k}?v={b[k]}" if k in b else KINDS[k]["placeholder"],
                "label": v["label"], "use": v["use"]} for k, v in KINDS.items()}


@public.get("/{kind}")
def branding_file(kind: str, db: Session = Depends(get_db)):
    if kind not in KINDS:
        raise HTTPException(404, "Not found")
    fid = _branding(db).get(kind)
    f = db.get(StoredFile, fid) if fid else None
    if not f:
        if not KINDS[kind]["placeholder"]:
            raise HTTPException(404, "No logo uploaded")
        return RedirectResponse(KINDS[kind]["placeholder"], status_code=307)
    ext = "." + f.original_name.rsplit(".", 1)[-1].lower()
    return Response(read_file(f), media_type=MIME.get(ext, "application/octet-stream"), headers={
        "Cache-Control": "public, max-age=86400",
        # an SVG opened directly can never run script or load anything
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    })


@admin.post("/{kind}")
async def upload(kind: str, file: UploadFile = File(...), cu: CurrentUser = Depends(require("admin.branding")),
                 db: Session = Depends(get_db)):
    if kind not in KINDS:
        raise HTTPException(404, "Unknown logo type")
    data = await file.read()
    ext = _check(kind, file.filename or "", data)
    f = save_file(db, data, f"{kind}{ext}", "branding", cu.id, MIME[ext], allowed=set(MIME))
    b = dict(_branding(db))
    b[kind] = f.id
    set_setting(db, "branding", b)
    audit(db, cu.user, "branding.logo_uploaded", "branding", kind, file=file.filename, size=len(data))
    db.commit()
    return branding_info(db)


@admin.delete("/{kind}")
def remove(kind: str, cu: CurrentUser = Depends(require("admin.branding")), db: Session = Depends(get_db)):
    b = dict(_branding(db))
    if kind not in b:
        raise HTTPException(404, "No logo uploaded")
    b.pop(kind)
    set_setting(db, "branding", b)
    audit(db, cu.user, "branding.logo_removed", "branding", kind)
    db.commit()
    return branding_info(db)


def export_logo_bytes() -> bytes | None:
    """Logo for Word exports, or None when none is uploaded."""
    from app.db import SessionLocal
    with SessionLocal() as db:
        fid = _branding(db).get("export")
        f = db.get(StoredFile, fid) if fid else None
        return read_file(f) if f else None
