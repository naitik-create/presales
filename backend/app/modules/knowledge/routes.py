import io
import re
import zipfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import embeddings, retrieval
from app.core.audit import audit
from app.core.deps import CurrentUser, get_current_user, require
from app.core.jobs import enqueue
from app.core.permissions import section_permission
from app.core.storage import read_file, save_file
from app.db import get_db, utcnow
from app.models.core import Job, Permission, Role, StoredFile
from app.models.knowledge import (DocumentChunk, DocumentVersion, KnowledgeSection, KnowledgeSource, SourceApproval,
                                  SubmittedRequirementResponse, SubmittedRFP)
from app.modules.knowledge import prebid_sheet, site_sync, sites
from app.modules.knowledge.compliance_sheet import parse_compliance_sheet, preview_compliance_sheet
from app.modules.knowledge.service import domain_allowed, section_stats
from app.parsing.extract import ExtractionError, extract

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _section_or_403(db: Session, cu: CurrentUser, section_id: int) -> KnowledgeSection:
    sec = db.get(KnowledgeSection, section_id)
    if not sec:
        raise HTTPException(404, "Section not found")
    if sec.key not in cu.section_keys() and not cu.has("knowledge.manage_sections"):
        raise HTTPException(403, "You do not have access to this section")
    return sec


def source_out(s: KnowledgeSource, sec: KnowledgeSection | None = None) -> dict:
    return {"id": s.id, "section_id": s.section_id, "section": sec.name if sec else None, "kind": s.kind,
            "title": s.title, "url": s.url, "product": s.product, "product_version": s.product_version,
            "document_type": s.document_type, "publication_date": s.publication_date, "label": s.label,
            "status": s.status, "ingest_status": s.ingest_status, "ingest_error": s.ingest_error,
            "current_version": s.current_version, "last_fetch_ok_at": s.last_fetch_ok_at,
            "last_fetch_attempt_at": s.last_fetch_attempt_at, "duplicate_of": s.duplicate_of,
            "created_at": s.created_at, "approved_at": s.approved_at}


# ---------- sections ----------
class SectionIn(BaseModel):
    name: str
    description: str = ""
    used_by: str = ""
    priority: int = 1
    enabled: bool = True
    sort: int = 100


@router.get("/sections")
def list_sections(cu: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    keys = cu.section_keys()
    stats = section_stats(db)
    rows = db.scalars(select(KnowledgeSection).order_by(KnowledgeSection.sort, KnowledgeSection.name)).all()
    return [{"id": s.id, "key": s.key, "name": s.name, "description": s.description, "used_by": s.used_by,
             "priority": s.priority, "enabled": s.enabled, "counts": stats.get(s.id, {})}
            for s in rows if s.key in keys or cu.has("knowledge.manage_sections")]


@router.post("/sections")
def create_section(body: SectionIn, cu: CurrentUser = Depends(require("knowledge.manage_sections")), db: Session = Depends(get_db)):
    key = re.sub(r"[^a-z0-9]+", "_", body.name.lower()).strip("_")[:50]
    if db.scalar(select(KnowledgeSection).where(KnowledgeSection.key == key)):
        raise HTTPException(400, "A section with this name exists")
    sec = KnowledgeSection(key=key, **body.model_dump())
    db.add(sec)
    perm = Permission(code=section_permission(key), area="Knowledge Hub", label=f"View section: {body.name}")
    db.add(perm)
    db.flush()
    # Roles that can already see every section also see the new one
    all_keys = {section_permission(s.key) for s in db.scalars(select(KnowledgeSection)) if s.key != key}
    for role in db.scalars(select(Role)):
        if all_keys and all_keys <= {p.code for p in role.permissions}:
            role.permissions.append(perm)
    audit(db, cu.user, "knowledge.section_created", "section", sec.id, name=body.name)
    db.commit()
    return {"id": sec.id, "key": key}


@router.patch("/sections/{section_id}")
def update_section(section_id: int, body: SectionIn, cu: CurrentUser = Depends(require("knowledge.manage_sections")),
                   db: Session = Depends(get_db)):
    sec = db.get(KnowledgeSection, section_id) or _404()
    for k, v in body.model_dump().items():
        setattr(sec, k, v)
    perm = db.get(Permission, section_permission(sec.key))
    if perm:
        perm.label = f"View section: {body.name}"
    audit(db, cu.user, "knowledge.section_updated", "section", sec.id, **body.model_dump())
    db.commit()
    return {"ok": True}


# ---------- sources ----------
@router.get("/sources")
def list_sources(section_id: int | None = None, status: str | None = None, q: str | None = None,
                 cu: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    keys = cu.section_keys()
    query = select(KnowledgeSource, KnowledgeSection).join(KnowledgeSection, KnowledgeSection.id == KnowledgeSource.section_id)
    if not cu.has("knowledge.manage_sections"):
        query = query.where(KnowledgeSection.key.in_(keys))
    if section_id:
        query = query.where(KnowledgeSource.section_id == section_id)
    if status:
        query = query.where(KnowledgeSource.status == status)
    if q:
        query = query.where(KnowledgeSource.title.ilike(f"%{q}%"))
    query = query.where(KnowledgeSource.kind != "page")  # pages are listed under their docs site
    return [source_out(s, sec) for s, sec in db.execute(query.order_by(KnowledgeSource.updated_at.desc()).limit(500))]


@router.get("/sources/{source_id}")
def get_source(source_id: int, cu: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(KnowledgeSource, source_id) or _404()
    sec = _section_or_403(db, cu, s.section_id)
    versions = db.scalars(select(DocumentVersion).where(DocumentVersion.source_id == s.id).order_by(DocumentVersion.version.desc())).all()
    approvals = db.scalars(select(SourceApproval).where(SourceApproval.source_id == s.id).order_by(SourceApproval.at.desc())).all()
    chunks = db.scalar(select(func.count()).select_from(DocumentChunk).where(DocumentChunk.source_id == s.id))
    jobs = db.scalars(select(Job).where(Job.kind == "knowledge.ingest", Job.ref_type == "knowledge_source",
                                        Job.ref_id == s.id).order_by(Job.id.desc()).limit(5)).all()
    return {**source_out(s, sec), "chunks": chunks,
            "versions": [{"version": v.version, "file_id": v.file_id, "sha256": v.sha256, "page_count": v.page_count,
                          "used_ocr": v.used_ocr, "embedding_model": v.embedding_model, "created_at": v.created_at}
                         for v in versions],
            "history": [{"action": a.action, "by": a.by_user, "note": a.note, "at": a.at} for a in approvals],
            "jobs": [{"id": j.id, "status": j.status, "progress": j.progress, "message": j.message,
                      "error": j.error.split("\n")[0] if j.error else ""} for j in jobs]}


def _new_version(db: Session, s: KnowledgeSource, file: StoredFile | None, user_id: int) -> Job:
    n = (db.scalar(select(func.max(DocumentVersion.version)).where(DocumentVersion.source_id == s.id)) or 0) + 1
    v = DocumentVersion(source_id=s.id, version=n, file_id=file.id if file else None, sha256=file.sha256 if file else "")
    db.add(v)
    db.flush()
    s.ingest_status = "Queued"
    return enqueue(db, "knowledge.ingest", {"version_id": v.id}, user_id=user_id, ref_type="knowledge_source", ref_id=s.id)


@router.post("/sources/upload")
async def upload_source(section_id: int = Form(...), title: str = Form(""), product: str = Form("Both"),
                        product_version: str = Form(""), document_type: str = Form(""), label: str = Form(""),
                        publication_date: date | None = Form(None), file: UploadFile = File(...),
                        cu: CurrentUser = Depends(require("knowledge.upload")), db: Session = Depends(get_db)):
    _section_or_403(db, cu, section_id)
    data = await file.read()
    f = save_file(db, data, file.filename or "upload", "knowledge", cu.id, file.content_type or "")
    dup = db.execute(select(KnowledgeSource).join(DocumentVersion, DocumentVersion.source_id == KnowledgeSource.id)
                     .where(DocumentVersion.sha256 == f.sha256)).scalars().first()
    s = KnowledgeSource(section_id=section_id, kind="file", title=title or f.original_name, product=product,
                        product_version=product_version, document_type=document_type, label=label,
                        publication_date=publication_date, created_by=cu.id, duplicate_of=dup.id if dup else None)
    db.add(s)
    db.flush()
    job = _new_version(db, s, f, cu.id)
    audit(db, cu.user, "knowledge.uploaded", "knowledge_source", s.id, title=s.title, file=f.original_name,
          duplicate_of=dup.id if dup else None)
    db.commit()
    return {**source_out(s), "job_id": job.id,
            "warning": f"This file is identical to an existing source: {dup.title}" if dup else None}


@router.post("/sources/{source_id}/versions")
async def upload_new_version(source_id: int, file: UploadFile = File(...), cu: CurrentUser = Depends(require("knowledge.upload")),
                             db: Session = Depends(get_db)):
    s = db.get(KnowledgeSource, source_id) or _404()
    _section_or_403(db, cu, s.section_id)
    if s.kind != "file":
        raise HTTPException(400, "URL sources are updated with re-sync")
    f = save_file(db, await file.read(), file.filename or "upload", "knowledge", cu.id, file.content_type or "")
    job = _new_version(db, s, f, cu.id)
    s.status = "Pending"  # a new version needs approval again
    audit(db, cu.user, "knowledge.new_version", "knowledge_source", s.id, file=f.original_name)
    db.commit()
    return {"job_id": job.id}


class UrlIn(BaseModel):
    section_id: int
    url: str
    title: str = ""
    product: str = "Both"
    product_version: str = ""
    document_type: str = "Online documentation"
    label: str = ""


@router.post("/sources/url")
def register_url(body: UrlIn, cu: CurrentUser = Depends(require("knowledge.register_url")), db: Session = Depends(get_db)):
    _section_or_403(db, cu, body.section_id)
    if not domain_allowed(db, body.url):
        raise HTTPException(400, "This domain is not on the allowed list. An administrator can add it in Settings.")
    if db.scalar(select(KnowledgeSource).where(KnowledgeSource.url == body.url)):
        raise HTTPException(400, "This URL is already registered")
    s = KnowledgeSource(section_id=body.section_id, kind="url", url=body.url, title=body.title or body.url,
                        product=body.product, product_version=body.product_version, document_type=body.document_type,
                        label=body.label, created_by=cu.id)
    db.add(s)
    db.flush()
    job = _new_version(db, s, None, cu.id)
    audit(db, cu.user, "knowledge.url_registered", "knowledge_source", s.id, url=body.url)
    db.commit()
    return {**source_out(s), "job_id": job.id}


@router.post("/sources/{source_id}/resync")
def resync(source_id: int, cu: CurrentUser = Depends(require("knowledge.register_url")), db: Session = Depends(get_db)):
    s = db.get(KnowledgeSource, source_id) or _404()
    _section_or_403(db, cu, s.section_id)
    if s.kind == "site":
        return {"job_id": _site_job(db, s, cu, {"mode": "crawl"}).id}
    if s.kind != "url":
        raise HTTPException(400, "Only URL sources can be re-synced")
    job = _new_version(db, s, None, cu.id)
    audit(db, cu.user, "knowledge.resync", "knowledge_source", s.id)
    db.commit()
    return {"job_id": job.id}


class DecisionIn(BaseModel):
    note: str = ""


@router.post("/sources/{source_id}/{action}")
def decide(source_id: int, action: str, body: DecisionIn, cu: CurrentUser = Depends(require("knowledge.approve")),
           db: Session = Depends(get_db)):
    status = {"approve": "Approved", "reject": "Rejected", "disable": "Disabled", "enable": "Approved"}.get(action)
    if not status:
        raise HTTPException(404, "Unknown action")
    s = db.get(KnowledgeSource, source_id) or _404()
    if action in ("approve", "enable") and s.ingest_status != "Ready":
        raise HTTPException(400, "The source must finish ingestion before it can be approved")
    s.status = status
    if action == "approve":
        s.approved_by, s.approved_at = cu.id, utcnow()
    pages = site_sync.cascade_status(db, s, status, cu.id) if s.kind == "site" else 0
    db.add(SourceApproval(source_id=s.id, action=action, by_user=cu.id, note=body.note))
    audit(db, cu.user, f"knowledge.{action}", "knowledge_source", s.id, title=s.title, note=body.note, pages=pages)
    db.commit()
    return source_out(s)


@router.get("/sources/{source_id}/download")
def download(source_id: int, version: int | None = None, cu: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(KnowledgeSource, source_id) or _404()
    _section_or_403(db, cu, s.section_id)
    v = db.scalar(select(DocumentVersion).where(DocumentVersion.source_id == s.id,
                                                DocumentVersion.version == (version or s.current_version)))
    if not v or not v.file_id:
        raise HTTPException(404, "No file for this source")
    f = db.get(StoredFile, v.file_id)
    return Response(read_file(f), media_type=f.content_type or "application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{f.original_name}"'})


@router.get("/search")
def test_search(q: str, section: str | None = None, cu: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    hits = retrieval.search(db, q, cu.section_keys(), sections=[section] if section else None, top_k=10)
    return [{**h.citation(), "score": h.score, "text": h.text[:600]} for h in hits]


# ---------- documentation sites (whole-site crawl, ZIP import) ----------
class SiteIn(BaseModel):
    section_id: int
    url: str
    title: str = ""
    product: str = "Both"
    product_version: str = ""
    label: str = ""  # e.g. "Older product"
    page_limit: int = sites.DEFAULT_LIMIT
    delay_ms: int = sites.DEFAULT_DELAY_MS
    fetch_now: bool = True  # False when the server has no internet and the pages come as a ZIP


def _site_out(db: Session, s: KnowledgeSource, sec: KnowledgeSection | None = None) -> dict:
    cfg = site_sync.config(db, s.id)
    job = db.scalar(select(Job).where(Job.kind == "knowledge.site_sync", Job.ref_type == "knowledge_source",
                                      Job.ref_id == s.id).order_by(Job.id.desc()))
    return {**source_out(s, sec), "page_limit": cfg["page_limit"], "delay_ms": cfg["delay_ms"], "report": cfg["report"],
            "pages": site_sync.page_counts(db, s),
            "job": {"id": job.id, "status": job.status, "progress": job.progress, "message": job.message,
                    "error": job.error.split("\n")[0] if job.error else ""} if job else None}


def _site_job(db: Session, s: KnowledgeSource, cu: CurrentUser, payload: dict) -> Job:
    running = db.scalar(select(Job).where(Job.kind == "knowledge.site_sync", Job.ref_type == "knowledge_source",
                                          Job.ref_id == s.id, Job.status.in_(["Queued", "Processing"])))
    if running:
        raise HTTPException(400, "A sync is already queued or running for this site")
    s.ingest_status = "Queued"
    job = enqueue(db, "knowledge.site_sync", {"site_id": s.id, **payload}, user_id=cu.id, ref_type="knowledge_source",
                  ref_id=s.id)
    audit(db, cu.user, "knowledge.site_sync_started", "knowledge_source", s.id, mode=payload.get("mode"))
    db.commit()
    return job


def _site(db: Session, cu: CurrentUser, sid: int) -> tuple[KnowledgeSource, KnowledgeSection]:
    s = db.get(KnowledgeSource, sid)
    if not s or s.kind != "site":
        raise HTTPException(404, "Site not found")
    return s, _section_or_403(db, cu, s.section_id)


@router.get("/sites")
def list_sites(cu: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(KnowledgeSource, KnowledgeSection).join(KnowledgeSection, KnowledgeSection.id == KnowledgeSource.section_id)
                      .where(KnowledgeSource.kind == "site").order_by(KnowledgeSource.title)).all()
    keys = cu.section_keys()
    return [_site_out(db, s, sec) for s, sec in rows if sec.key in keys or cu.has("knowledge.manage_sections")]


@router.post("/sites")
def create_site(body: SiteIn, cu: CurrentUser = Depends(require("knowledge.register_url")), db: Session = Depends(get_db)):
    """Register a documentation site; its pages are found from the sitemap (or links) and indexed by a sync job."""
    _section_or_403(db, cu, body.section_id)
    try:
        base = sites.base_url(body.url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not domain_allowed(db, base):
        raise HTTPException(400, "This domain is not on the allowed list. An administrator can add it in Settings.")
    for other in db.scalars(select(KnowledgeSource).where(KnowledgeSource.kind == "site")):
        if base.startswith(other.url) or other.url.startswith(base):
            raise HTTPException(400, f"This overlaps the site already registered: {other.title} ({other.url})")
    s = KnowledgeSource(section_id=body.section_id, kind="site", url=base, title=body.title or base,
                        product=body.product, product_version=body.product_version, label=body.label,
                        document_type="Online documentation", created_by=cu.id, ingest_status="Ready" if not body.fetch_now else "Queued")
    db.add(s)
    db.flush()
    site_sync.save_config(db, s.id, {"page_limit": max(1, min(body.page_limit, sites.MAX_LIMIT)),
                                     "delay_ms": max(100, min(body.delay_ms, 5000))})
    audit(db, cu.user, "knowledge.site_registered", "knowledge_source", s.id, url=base)
    db.commit()
    job = _site_job(db, s, cu, {"mode": "crawl"}) if body.fetch_now else None
    return {**_site_out(db, s), "job_id": job.id if job else None}


class SiteUpdate(BaseModel):
    title: str | None = None
    product: str | None = None
    product_version: str | None = None
    label: str | None = None
    page_limit: int | None = None
    delay_ms: int | None = None


@router.patch("/sites/{sid}")
def update_site(sid: int, body: SiteUpdate, cu: CurrentUser = Depends(require("knowledge.register_url")),
                db: Session = Depends(get_db)):
    s, sec = _site(db, cu, sid)
    for k in ("title", "product", "product_version", "label"):
        v = getattr(body, k)
        if v is not None:
            setattr(s, k, v)
    if body.product is not None or body.product_version is not None or body.label is not None:
        for p in db.scalars(site_sync.pages_query(s)):  # pages carry the site's product and version into answers
            p.product, p.product_version, p.label = s.product, s.product_version, s.label
            db.execute(DocumentChunk.__table__.update().where(DocumentChunk.source_id == p.id).values(
                meta={"product": s.product, "version": s.product_version, "document_type": p.document_type}))
    cfg = {}
    if body.page_limit is not None:
        cfg["page_limit"] = max(1, min(body.page_limit, sites.MAX_LIMIT))
    if body.delay_ms is not None:
        cfg["delay_ms"] = max(100, min(body.delay_ms, 5000))
    if cfg:
        site_sync.save_config(db, s.id, cfg)
    audit(db, cu.user, "knowledge.site_updated", "knowledge_source", s.id, **{k: str(v) for k, v in body.model_dump().items() if v is not None})
    db.commit()
    return _site_out(db, s, sec)


@router.post("/sites/{sid}/sync")
def sync_site(sid: int, cu: CurrentUser = Depends(require("knowledge.register_url")), db: Session = Depends(get_db)):
    s, _sec = _site(db, cu, sid)
    return {"job_id": _site_job(db, s, cu, {"mode": "crawl"}).id}


@router.post("/sites/{sid}/import")
async def import_site_zip(sid: int, file: UploadFile = File(...), cu: CurrentUser = Depends(require("knowledge.upload")),
                          db: Session = Depends(get_db)):
    """Pages saved with the crawl script on a machine that has internet access."""
    s, _sec = _site(db, cu, sid)
    data = await file.read()
    try:
        m = sites.read_manifest(zipfile.ZipFile(io.BytesIO(data)).read(sites.ZIP_MANIFEST))
    except (KeyError, ValueError, zipfile.BadZipFile) as e:
        raise HTTPException(400, f"Not a ZIP made by the crawl script: {e}")
    if sites.base_url(m.get("base") or "") != s.url:
        raise HTTPException(400, f"This ZIP was made for {m.get('base')}, not {s.url}")
    f = save_file(db, data, file.filename or "site.zip", "knowledge", cu.id, "application/zip", allowed={".zip"})
    return {"job_id": _site_job(db, s, cu, {"mode": "zip", "file_id": f.id}).id, "pages": len(m["pages"])}


@router.get("/sites/{sid}/pages")
def site_pages(sid: int, q: str = "", status: str = "", offset: int = 0, cu: CurrentUser = Depends(get_current_user),
               db: Session = Depends(get_db)):
    s, _sec = _site(db, cu, sid)
    query = site_sync.pages_query(s)
    if q:
        query = query.where(KnowledgeSource.title.ilike(f"%{q}%") | KnowledgeSource.url.ilike(f"%{q}%"))
    if status == "Failed":
        query = query.where(KnowledgeSource.ingest_status == "Failed")
    elif status:
        query = query.where(KnowledgeSource.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(KnowledgeSource.url).offset(max(0, offset)).limit(100)).all()
    return {"total": total, "pages": [{"id": p.id, "title": p.title, "url": p.url, "status": p.status,
                                       "ingest_status": p.ingest_status, "error": p.ingest_error,
                                       "version": p.current_version, "fetched_at": p.last_fetch_ok_at} for p in rows]}


@router.get("/sites-crawl-script")
def crawl_script(cu: CurrentUser = Depends(require("knowledge.upload"))):
    """The stand-alone script that saves a docs site to a ZIP on a machine with internet access."""
    data = (Path(__file__).parent / "docs_crawl_to_zip.py").read_bytes()
    return Response(data, media_type="text/x-python",
                    headers={"Content-Disposition": 'attachment; filename="docs_crawl_to_zip.py"'})


# ---------- past pre-bid query sheets ----------
def _sheet_rows(data: bytes, name: str) -> list[tuple[str, str, list[str]]]:
    try:
        return [(seg.section, seg.ref, list(seg.cells)) for seg in extract(data, name).segments]
    except ExtractionError as e:
        raise HTTPException(400, str(e))


@router.post("/prebid/preview")
async def preview_prebid(file: UploadFile = File(...), cu: CurrentUser = Depends(require("knowledge.upload"))):
    """What an import would read from a past pre-bid query sheet: the detected columns and the first queries."""
    queries, cols = prebid_sheet.parse_rows(_sheet_rows(await file.read(), file.filename or "sheet.xlsx"))
    return {"columns": cols, "queries": len(queries), "sample": queries[:5]}


@router.post("/prebid")
async def import_prebid(customer: str = Form(...), tender: str = Form(""), date_text: str = Form(""),
                        outcome: str = Form(""), product: str = Form("Both"), file: UploadFile = File(...),
                        cu: CurrentUser = Depends(require("knowledge.upload")), db: Session = Depends(get_db)):
    """Store a past pre-bid query sheet as knowledge (Internal presales knowledge, awaiting approval)."""
    sec = db.scalar(select(KnowledgeSection).where(KnowledgeSection.key == "internal_presales_knowledge"))
    if not sec:
        raise HTTPException(400, "The Internal presales knowledge section does not exist")
    _section_or_403(db, cu, sec.id)
    data = await file.read()
    queries, _cols = prebid_sheet.parse_rows(_sheet_rows(data, file.filename or "sheet.xlsx"))
    if not queries:
        raise HTTPException(400, "No pre-bid queries found: the sheet needs a header row with a Query / Clarification column")
    original = save_file(db, data, file.filename or "prebid.xlsx", "knowledge", cu.id, file.content_type or "")
    md = prebid_sheet.to_markdown({"customer": customer, "tender": tender, "date": date_text, "outcome": outcome}, queries)
    title = f"{prebid_sheet.TITLE_PREFIX}{customer}" + (f" ({tender})" if tender else "")
    f = save_file(db, md.encode("utf-8"), f"{re.sub(r'[^A-Za-z0-9 ._-]+', '', title)[:120]}.md", "knowledge", cu.id,
                  "text/markdown", allowed={".md"})
    s = KnowledgeSource(section_id=sec.id, kind="file", title=title[:300], product=product,
                        document_type="Past pre-bid queries", label="internal", created_by=cu.id)
    db.add(s)
    db.flush()
    job = _new_version(db, s, f, cu.id)
    audit(db, cu.user, "knowledge.prebid_imported", "knowledge_source", s.id, customer=customer, queries=len(queries),
          original_file=original.id)
    db.commit()
    return {**source_out(s, sec), "job_id": job.id, "queries": len(queries)}


@router.post("/submitted/preview")
async def preview_submitted(compliance_sheet: UploadFile = File(...), cu: CurrentUser = Depends(require("submitted.upload"))):
    """Check a past compliance sheet before importing: detected columns, number of rows, a sample."""
    data = await compliance_sheet.read()
    try:
        return preview_compliance_sheet(data, compliance_sheet.filename or "sheet.xlsx")
    except ExtractionError as e:
        raise HTTPException(400, str(e))


# ---------- Submitted RFP repository (§6.4) ----------
def _submitted_out(r: SubmittedRFP, pairs: int) -> dict:
    return {"id": r.id, "customer": r.customer, "industry": r.industry, "submitted_on": r.submitted_on,
            "product_version": r.product_version, "title": r.title, "held_back_for_testing": r.held_back_for_testing,
            "workspace_id": r.workspace_id, "files": r.file_ids, "pairs": pairs}


@router.get("/submitted")
def list_submitted(cu: CurrentUser = Depends(require("submitted.view")), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(SubmittedRequirementResponse.submitted_rfp_id, func.count())
                             .group_by(SubmittedRequirementResponse.submitted_rfp_id)).all())
    return [_submitted_out(r, counts.get(r.id, 0)) for r in db.scalars(select(SubmittedRFP).order_by(SubmittedRFP.submitted_on.desc().nullslast()))]


@router.post("/submitted")
async def create_submitted(customer: str = Form(...), industry: str = Form(""), submitted_on: date | None = Form(None),
                           product_version: str = Form(""), title: str = Form(""), held_back_for_testing: bool = Form(False),
                           compliance_sheet: UploadFile | None = File(None), documents: list[UploadFile] = File(default=[]),
                           cu: CurrentUser = Depends(require("submitted.upload")), db: Session = Depends(get_db)):
    r = SubmittedRFP(customer=customer, industry=industry, submitted_on=submitted_on, product_version=product_version,
                     title=title or customer, held_back_for_testing=held_back_for_testing, created_by=cu.id, file_ids=[])
    db.add(r)
    db.flush()
    files = []
    for d in documents:
        f = save_file(db, await d.read(), d.filename or "document", "submitted", cu.id, d.content_type or "")
        files.append({"file_id": f.id, "name": f.original_name, "role": "document"})
    n = 0
    if compliance_sheet is not None and compliance_sheet.filename:
        data = await compliance_sheet.read()
        f = save_file(db, data, compliance_sheet.filename, "submitted", cu.id, compliance_sheet.content_type or "")
        files.append({"file_id": f.id, "name": f.original_name, "role": "compliance"})
        n = add_pairs(db, r.id, parse_compliance_sheet(data, f.original_name))
    r.file_ids = files
    audit(db, cu.user, "submitted.created", "submitted_rfp", r.id, customer=customer, pairs=n, held_back=held_back_for_testing)
    db.commit()
    return _submitted_out(r, n)


def add_pairs(db: Session, submitted_id: int, pairs: list[dict]) -> int:
    cfg = embeddings.active_config(db)
    vecs = embeddings.embed(cfg, [p["requirement"] for p in pairs]) if cfg and pairs else [None] * len(pairs)
    for p, v in zip(pairs, vecs):
        db.add(SubmittedRequirementResponse(submitted_rfp_id=submitted_id, requirement=p["requirement"],
                                            status=p.get("status", ""), response=p.get("response", ""),
                                            reference=p.get("reference", ""), embedding=v,
                                            embedding_model=cfg.model_name if cfg else ""))
    return len(pairs)


@router.get("/submitted/{rid}")
def get_submitted(rid: int, cu: CurrentUser = Depends(require("submitted.view")), db: Session = Depends(get_db)):
    r = db.get(SubmittedRFP, rid) or _404()
    pairs = db.scalars(select(SubmittedRequirementResponse).where(SubmittedRequirementResponse.submitted_rfp_id == rid)
                       .order_by(SubmittedRequirementResponse.id)).all()
    return {**_submitted_out(r, len(pairs)), "pairs": [{"id": p.id, "requirement": p.requirement, "status": p.status,
                                                         "response": p.response, "reference": p.reference} for p in pairs]}


@router.patch("/submitted/{rid}")
def update_submitted(rid: int, held_back_for_testing: bool, cu: CurrentUser = Depends(require("submitted.manage")),
                     db: Session = Depends(get_db)):
    r = db.get(SubmittedRFP, rid) or _404()
    r.held_back_for_testing = held_back_for_testing
    audit(db, cu.user, "submitted.updated", "submitted_rfp", r.id, held_back=held_back_for_testing)
    db.commit()
    return {"ok": True}


@router.delete("/submitted/{rid}")
def delete_submitted(rid: int, cu: CurrentUser = Depends(require("submitted.manage")), db: Session = Depends(get_db)):
    r = db.get(SubmittedRFP, rid) or _404()
    audit(db, cu.user, "submitted.deleted", "submitted_rfp", r.id, customer=r.customer)
    db.delete(r)
    db.commit()
    return {"ok": True}


@router.get("/submitted/files/{file_id}")
def submitted_file(file_id: int, cu: CurrentUser = Depends(require("submitted.view")), db: Session = Depends(get_db)):
    f = db.get(StoredFile, file_id)
    if not f or f.area != "submitted":
        raise HTTPException(404, "Not found")
    return Response(read_file(f), media_type=f.content_type or "application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{f.original_name}"'})


def _404():
    raise HTTPException(404, "Not found")
