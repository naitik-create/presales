import re
from datetime import date

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
from app.modules.knowledge.compliance_sheet import parse_compliance_sheet
from app.modules.knowledge.service import domain_allowed, section_stats

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
    db.add(SourceApproval(source_id=s.id, action=action, by_user=cu.id, note=body.note))
    audit(db, cu.user, f"knowledge.{action}", "knowledge_source", s.id, title=s.title, note=body.note)
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
