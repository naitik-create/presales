import json
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import client as ai
from app.ai import retrieval
from app.core.audit import audit
from app.core.deps import CurrentUser, require
from app.core.jobs import JobContext, QueueFull, enqueue, handler
from app.core.settings_store import get_setting
from app.core.storage import read_file, save_file
from app.db import get_db, utcnow
from app.exports.templates import fill, find_placeholders
from app.models.core import CustomerContext, Job, StoredFile
from app.models.knowledge import KnowledgeSection, SubmittedRFP
from app.models.rfp import (RFPAgentRun, RFPComplianceResponse, RFPDocument, RFPProposal, RFPRequirement, RFPTemplate,
                            RFPWorkspace)
from app.modules.knowledge.routes import add_pairs
from app.modules.rfp import agents as A
from app.modules.rfp import exports, hwsizing
from app.modules.rfp.service import compliance_digest, workspace_cost
from app.parsing.extract import docx_to_pdf, extract

router = APIRouter(prefix="/rfp", tags=["rfp"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
RFP_EXT = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv", ".txt", ".zip"}


def _ws(db: Session, wid: int) -> RFPWorkspace:
    ws = db.get(RFPWorkspace, wid)
    if not ws:
        raise HTTPException(404, "Workspace not found")
    return ws


def ws_out(db: Session, ws: RFPWorkspace, customer: str = "") -> dict:
    job = db.scalar(select(Job).where(Job.ref_type == "rfp_workspace", Job.ref_id == ws.id).order_by(Job.id.desc()))
    return {"id": ws.id, "name": ws.name, "customer_id": ws.customer_id, "customer": customer, "status": ws.status,
            "product_version": ws.product_version, "products": ws.products, "due_date": ws.due_date,
            "template_id": ws.template_id, "revision": ws.revision, "submitted_at": ws.submitted_at,
            "updated_at": ws.updated_at, "estimated_cost": workspace_cost(db, ws.id),
            "job": {"id": job.id, "kind": job.kind, "status": job.status, "progress": job.progress, "message": job.message,
                    "error": job.error.split("\n")[0] if job.error else ""} if job else None}


class WorkspaceIn(BaseModel):
    name: str
    customer_id: int | None = None
    product_version: str = ""
    products: list[str] = ["ObserveOps", "ServiceOps"]
    due_date: date | None = None


@router.get("/workspaces")
def list_workspaces(cu: CurrentUser = Depends(require("rfp.view")), db: Session = Depends(get_db)):
    rows = db.execute(select(RFPWorkspace, CustomerContext.name).outerjoin(CustomerContext, CustomerContext.id == RFPWorkspace.customer_id)
                      .order_by(RFPWorkspace.updated_at.desc()).limit(300)).all()
    return [ws_out(db, w, n or "") for w, n in rows]


@router.post("/workspaces")
def create_workspace(body: WorkspaceIn, cu: CurrentUser = Depends(require("rfp.create")), db: Session = Depends(get_db)):
    ws = RFPWorkspace(**body.model_dump(), created_by=cu.id)
    db.add(ws)
    db.flush()
    audit(db, cu.user, "rfp.workspace_created", "rfp_workspace", ws.id, name=ws.name)
    db.commit()
    return {"id": ws.id}


@router.get("/workspaces/{wid}")
def get_workspace(wid: int, cu: CurrentUser = Depends(require("rfp.view")), db: Session = Depends(get_db)):
    ws = _ws(db, wid)
    customer = db.get(CustomerContext, ws.customer_id).name if ws.customer_id else ""
    docs = db.scalars(select(RFPDocument).where(RFPDocument.workspace_id == wid).order_by(RFPDocument.id)).all()
    counts = dict(db.execute(select(RFPComplianceResponse.status, func.count())
                             .join(RFPRequirement, RFPRequirement.id == RFPComplianceResponse.requirement_id)
                             .where(RFPRequirement.workspace_id == wid, RFPRequirement.active.is_(True))
                             .group_by(RFPComplianceResponse.status)).all())
    return {**ws_out(db, ws, customer),
            "documents": [{"id": d.id, "name": d.name, "role": d.role, "revision": d.revision, "status": d.status,
                           "used_ocr": d.used_ocr, "segments": len(d.extracted or []), "uploaded_at": d.uploaded_at} for d in docs],
            "status_counts": counts}


@router.patch("/workspaces/{wid}")
def update_workspace(wid: int, body: dict, cu: CurrentUser = Depends(require("rfp.edit")), db: Session = Depends(get_db)):
    ws = _ws(db, wid)
    for k in ("name", "product_version", "products", "due_date", "template_id", "customer_id"):
        if k in body:
            setattr(ws, k, body[k])
    audit(db, cu.user, "rfp.workspace_updated", "rfp_workspace", ws.id, **{k: str(v) for k, v in body.items()})
    db.commit()
    return {"ok": True}


@router.post("/workspaces/{wid}/documents")
async def upload_documents(wid: int, role: str = Form("rfp"), files: list[UploadFile] = File(...),
                           cu: CurrentUser = Depends(require("rfp.edit")), db: Session = Depends(get_db)):
    ws = _ws(db, wid)
    limits = get_setting(db, "rfp_limits")
    have = db.scalar(select(func.count()).select_from(RFPDocument).where(RFPDocument.workspace_id == wid)) or 0
    if have + len(files) > limits["max_documents_per_rfp"]:
        raise HTTPException(400, f"A workspace can hold at most {limits['max_documents_per_rfp']} documents")
    if role in ("corrigendum", "revised"):
        ws.revision += 1
    saved = []
    for up in files:
        data = await up.read()
        if len(data) > limits["max_document_mb"] * 1024 * 1024:
            raise HTTPException(400, f"{up.filename} is larger than {limits['max_document_mb']} MB")
        allowed = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".zip"} if role == "submitted" else RFP_EXT
        f = save_file(db, data, up.filename or "document", "rfp", cu.id, up.content_type or "", allowed=allowed)
        d = RFPDocument(workspace_id=wid, file_id=f.id, name=f.original_name, role="rfp" if role == "revised" else role,
                        revision=ws.revision)
        db.add(d)
        saved.append(f.original_name)
    audit(db, cu.user, "rfp.documents_uploaded", "rfp_workspace", wid, files=saved, role=role, revision=ws.revision)
    db.commit()
    return {"uploaded": saved, "revision": ws.revision}


@router.get("/documents/{did}/download")
def download_document(did: int, cu: CurrentUser = Depends(require("rfp.view")), db: Session = Depends(get_db)):
    d = db.get(RFPDocument, did) or _404()
    f = db.get(StoredFile, d.file_id)
    return Response(read_file(f), media_type=f.content_type or "application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{f.original_name}"'})


def _enqueue_rfp(db: Session, kind: str, ws: RFPWorkspace, cu: CurrentUser, **payload) -> Job:
    running = db.scalar(select(Job).where(Job.ref_type == "rfp_workspace", Job.ref_id == ws.id,
                                          Job.status.in_(["Queued", "Processing"])))
    if running:
        raise HTTPException(400, "A job is already queued or running for this workspace")
    try:
        job = enqueue(db, kind, {"workspace_id": ws.id, **payload}, user_id=cu.id, queue="rfp",
                      ref_type="rfp_workspace", ref_id=ws.id)
    except QueueFull as e:
        raise HTTPException(429, str(e)) from e
    if kind in ("rfp.process", "rfp.corrigendum"):
        ws.status = "Queued"
    return job


@router.post("/workspaces/{wid}/process")
def process(wid: int, cu: CurrentUser = Depends(require("rfp.edit")), db: Session = Depends(get_db)):
    ws = _ws(db, wid)
    if not db.scalar(select(RFPDocument).where(RFPDocument.workspace_id == wid, RFPDocument.role == "rfp")):
        raise HTTPException(400, "Upload the RFP documents first")
    approved = db.scalar(select(func.count()).select_from(RFPComplianceResponse)
                         .join(RFPRequirement, RFPRequirement.id == RFPComplianceResponse.requirement_id)
                         .where(RFPRequirement.workspace_id == wid, RFPComplianceResponse.approved.is_(True)))
    if approved:
        raise HTTPException(400, "This workspace has approved answers. Upload a revised RFP or corrigendum instead of re-processing.")
    job = _enqueue_rfp(db, "rfp.process", ws, cu)
    audit(db, cu.user, "rfp.processing_started", "rfp_workspace", wid, job_id=job.id)
    db.commit()
    return {"job_id": job.id}


@router.post("/workspaces/{wid}/corrigendum")
def process_corrigendum(wid: int, mode: str = "corrigendum", cu: CurrentUser = Depends(require("rfp.edit")), db: Session = Depends(get_db)):
    ws = _ws(db, wid)
    if mode not in ("corrigendum", "revised"):
        raise HTTPException(400, "Mode must be corrigendum or revised")
    job = _enqueue_rfp(db, "rfp.corrigendum", ws, cu, mode=mode)
    audit(db, cu.user, "rfp.corrigendum_started", "rfp_workspace", wid, mode=mode, revision=ws.revision)
    db.commit()
    return {"job_id": job.id}


@router.post("/workspaces/{wid}/agents/{agent}/run")
def rerun(wid: int, agent: str, body: dict | None = None, cu: CurrentUser = Depends(require("rfp.edit")), db: Session = Depends(get_db)):
    ws = _ws(db, wid)
    if agent not in (*A.DOC_AGENTS, "compliance"):
        raise HTTPException(404, "Unknown agent")
    job = _enqueue_rfp(db, "rfp.agent", ws, cu, agent=agent, requirement_ids=(body or {}).get("requirement_ids"))
    audit(db, cu.user, "rfp.agent_rerun", "rfp_workspace", wid, agent=agent)
    db.commit()
    return {"job_id": job.id}


# ---------- requirements & answers ----------
def req_out(r: RFPRequirement, c: RFPComplianceResponse | None) -> dict:
    return {"id": r.id, "number": r.number, "text": r.text, "category": r.category, "source_file": r.source_file,
            "source_ref": r.source_ref, "revision": r.revision, "change": r.change, "active": r.active,
            "answer": None if c is None else {
                "id": c.id, "status": c.status, "response": c.response, "explanation": c.explanation, "evidence": c.evidence,
                "sources": c.sources, "validation_remarks": c.validation_remarks, "origin": c.origin,
                "origin_detail": c.origin_detail, "approved": c.approved, "approved_at": c.approved_at}}


@router.get("/workspaces/{wid}/requirements")
def requirements(wid: int, status: str | None = None, category: str | None = None, change: str | None = None,
                 approved: bool | None = None, q: str | None = None, include_removed: bool = False,
                 cu: CurrentUser = Depends(require("rfp.view")), db: Session = Depends(get_db)):
    query = (select(RFPRequirement, RFPComplianceResponse)
             .outerjoin(RFPComplianceResponse, RFPComplianceResponse.requirement_id == RFPRequirement.id)
             .where(RFPRequirement.workspace_id == wid))
    if not include_removed:
        query = query.where(RFPRequirement.active.is_(True))
    if status:
        query = query.where(RFPComplianceResponse.status == status)
    if category:
        query = query.where(RFPRequirement.category == category)
    if change:
        query = query.where(RFPRequirement.change == change)
    if approved is not None:
        query = query.where(RFPComplianceResponse.approved.is_(approved))
    if q:
        query = query.where(RFPRequirement.text.ilike(f"%{q}%"))
    return [req_out(r, c) for r, c in db.execute(query.order_by(RFPRequirement.id))]


class AnswerIn(BaseModel):
    status: str
    response: str
    explanation: str = ""
    evidence: str = ""
    validation_remarks: str = ""


@router.put("/requirements/{rid}/answer")
def edit_answer(rid: int, body: AnswerIn, cu: CurrentUser = Depends(require("rfp.edit")), db: Session = Depends(get_db)):
    r = db.get(RFPRequirement, rid) or _404()
    if body.status not in A.COMPLIANCE_STATUSES:
        raise HTTPException(400, "Unknown status")
    c = db.scalar(select(RFPComplianceResponse).where(RFPComplianceResponse.requirement_id == rid))
    if c is None:
        c = RFPComplianceResponse(requirement_id=rid, origin="manual")
        db.add(c)
    if c.approved and not cu.has("rfp.approve"):
        raise HTTPException(403, "This answer is approved; only an approver can change it")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    c.approved = False
    audit(db, cu.user, "rfp.answer_edited", "rfp_requirement", rid, status=body.status)
    db.commit()
    return req_out(r, c)


class RequirementIn(BaseModel):
    text: str
    category: str = "Technical"
    source_ref: str = ""


@router.put("/requirements/{rid}")
def edit_requirement(rid: int, body: RequirementIn, cu: CurrentUser = Depends(require("rfp.edit")), db: Session = Depends(get_db)):
    r = db.get(RFPRequirement, rid) or _404()
    r.text, r.category, r.source_ref = body.text, body.category, body.source_ref or r.source_ref
    audit(db, cu.user, "rfp.requirement_edited", "rfp_requirement", rid)
    db.commit()
    return {"ok": True}


class ApproveIn(BaseModel):
    requirement_ids: list[int]
    approved: bool = True


@router.post("/workspaces/{wid}/approve")
def approve(wid: int, body: ApproveIn, cu: CurrentUser = Depends(require("rfp.approve")), db: Session = Depends(get_db)):
    rows = db.scalars(select(RFPComplianceResponse).join(RFPRequirement, RFPRequirement.id == RFPComplianceResponse.requirement_id)
                      .where(RFPRequirement.workspace_id == wid, RFPRequirement.id.in_(body.requirement_ids))).all()
    for c in rows:
        c.approved = body.approved
        c.approved_by, c.approved_at = (cu.id, utcnow()) if body.approved else (None, None)
    audit(db, cu.user, "rfp.answers_approved" if body.approved else "rfp.answers_unapproved", "rfp_workspace", wid,
          count=len(rows), requirement_ids=body.requirement_ids[:500])
    db.commit()
    return {"updated": len(rows)}


# ---------- document-level agent outputs ----------
@router.get("/workspaces/{wid}/agents")
def agent_outputs(wid: int, cu: CurrentUser = Depends(require("rfp.view")), db: Session = Depends(get_db)):
    out = {}
    for key in A.DOC_AGENTS:
        run = db.scalar(select(RFPAgentRun).where(RFPAgentRun.workspace_id == wid, RFPAgentRun.agent_key == key)
                        .order_by(RFPAgentRun.id.desc()))
        if run:
            out[key] = {"id": run.id, "label": A.DOC_AGENT_LABELS[key], "output": run.edited_output or run.output,
                        "edited": run.edited_output is not None, "approved": run.approved, "at": run.at, "revision": run.revision}
    return out


@router.put("/agent-runs/{run_id}")
def edit_agent_output(run_id: int, body: dict, cu: CurrentUser = Depends(require("rfp.edit")), db: Session = Depends(get_db)):
    run = db.get(RFPAgentRun, run_id) or _404()
    run.edited_output = body.get("output")
    run.approved = False
    audit(db, cu.user, "rfp.agent_output_edited", "rfp_agent_run", run_id, agent=run.agent_key)
    db.commit()
    return {"ok": True}


@router.post("/agent-runs/{run_id}/approve")
def approve_agent_output(run_id: int, cu: CurrentUser = Depends(require("rfp.approve")), db: Session = Depends(get_db)):
    run = db.get(RFPAgentRun, run_id) or _404()
    run.approved = True
    audit(db, cu.user, "rfp.agent_output_approved", "rfp_agent_run", run_id, agent=run.agent_key)
    db.commit()
    return {"ok": True}


@router.post("/workspaces/{wid}/sizing")
def resize(wid: int, body: dict, cu: CurrentUser = Depends(require("rfp.edit")), db: Session = Depends(get_db)):
    """Recompute Motadata hardware sizing from edited inputs ([{name, value, ref, note}]) and save it on the latest
    architecture run as an edit (which needs approval again)."""
    ws = _ws(db, wid)
    run = db.scalar(select(RFPAgentRun).where(RFPAgentRun.workspace_id == wid, RFPAgentRun.agent_key == "architecture")
                    .order_by(RFPAgentRun.id.desc()))
    if not run:
        raise HTTPException(400, "Run the architecture and sizing agent first")
    items = [i for i in (body.get("inputs") or []) if isinstance(i, dict)]
    for i in items:
        try:
            i["value"] = float(i.get("value") or 0)
        except (TypeError, ValueError):
            raise HTTPException(400, f"{i.get('name')}: enter a number")
    out = dict(run.edited_output or run.output)
    out["motadata_inputs"] = items
    out["motadata_sizing"] = hwsizing.compute(items, ws.products or ["ObserveOps", "ServiceOps"])
    run.edited_output, run.approved = out, False
    audit(db, cu.user, "rfp.sizing_edited", "rfp_agent_run", run.id)
    db.commit()
    return out["motadata_sizing"]


def _latest_runs(db: Session, wid: int) -> dict:
    out = {}
    for key in A.DOC_AGENTS:
        run = db.scalar(select(RFPAgentRun).where(RFPAgentRun.workspace_id == wid, RFPAgentRun.agent_key == key)
                        .order_by(RFPAgentRun.id.desc()))
        if run:
            out[key] = run.edited_output or run.output
    return out


# ---------- templates & proposals ----------
@router.get("/templates")
def list_templates(module: str = "rfp", cu: CurrentUser = Depends(require("rfp.view", "demo.view")), db: Session = Depends(get_db)):
    return [{"id": t.id, "name": t.name, "kind": t.kind, "module": t.module, "placeholders": t.placeholders, "version": t.version,
             "active": t.active, "updated_at": t.updated_at}
            for t in db.scalars(select(RFPTemplate).where(RFPTemplate.module == module).order_by(RFPTemplate.name))]


@router.post("/templates")
async def upload_template(name: str = Form(...), kind: str = Form("template"), module: str = Form("rfp"),
                          template_id: int | None = Form(None), file: UploadFile = File(...),
                          cu: CurrentUser = Depends(require("rfp.manage_templates", "demo.manage_templates")), db: Session = Depends(get_db)):
    data = await file.read()
    allowed = {".docx"} if kind == "template" else {".docx", ".pdf", ".doc"}
    f = save_file(db, data, file.filename or "template.docx", "templates", cu.id, file.content_type or "", allowed=allowed)
    phs = [{"name": n, "description": n.replace("_", " ")} for n in find_placeholders(data)] if kind == "template" else []
    if kind == "template" and not phs:
        raise HTTPException(400, "No {{placeholders}} found. Add placeholders such as {{executive_summary}} to the template first.")
    if template_id:
        t = db.get(RFPTemplate, template_id) or _404()
        old = {p["name"]: p["description"] for p in t.placeholders}
        t.file_id, t.version, t.name = f.id, t.version + 1, name
        t.placeholders = [{"name": p["name"], "description": old.get(p["name"], p["description"])} for p in phs]
    else:
        t = RFPTemplate(name=name, kind=kind, module=module, file_id=f.id, placeholders=phs)
        db.add(t)
    db.flush()
    audit(db, cu.user, "rfp.template_saved", "rfp_template", t.id, name=name, version=t.version, placeholders=[p["name"] for p in phs])
    db.commit()
    return {"id": t.id, "placeholders": t.placeholders, "version": t.version}


@router.put("/templates/{tid}")
def update_template(tid: int, body: dict, cu: CurrentUser = Depends(require("rfp.manage_templates", "demo.manage_templates")),
                    db: Session = Depends(get_db)):
    t = db.get(RFPTemplate, tid) or _404()
    if "placeholders" in body:
        t.placeholders = body["placeholders"]
    if "active" in body:
        t.active = bool(body["active"])
    if "name" in body:
        t.name = body["name"]
    audit(db, cu.user, "rfp.template_updated", "rfp_template", t.id)
    db.commit()
    return {"ok": True}


@router.post("/workspaces/{wid}/proposal")
def generate_proposal(wid: int, body: dict, cu: CurrentUser = Depends(require("rfp.edit")), db: Session = Depends(get_db)):
    ws = _ws(db, wid)
    tid = body.get("template_id") or ws.template_id
    t = db.get(RFPTemplate, tid) if tid else None
    if not t or t.kind != "template":
        raise HTTPException(400, "Select a proposal template")
    ws.template_id = t.id
    job = _enqueue_rfp(db, "rfp.proposal", ws, cu, template_id=t.id)
    db.commit()
    return {"job_id": job.id}


@handler("rfp.proposal")
def proposal_job(db: Session, job: Job, ctx: JobContext) -> dict:
    ws = db.get(RFPWorkspace, job.payload["workspace_id"])
    t = db.get(RFPTemplate, job.payload["template_id"])
    samples = db.scalars(select(RFPTemplate).where(RFPTemplate.kind == "sample", RFPTemplate.module == "rfp",
                                                   RFPTemplate.active.is_(True)).limit(2)).all()
    sample_text = ""
    for s in samples:
        f = db.get(StoredFile, s.file_id)
        ex = extract(read_file(f), f.original_name)
        sample_text += f'<sample name="{s.name}">\n' + "\n".join(seg.text for seg in ex.segments)[:30000] + "\n</sample>\n"
    runs = _latest_runs(db, ws.id)
    allowed = set(db.scalars(select(KnowledgeSection.key)))
    hits = retrieval.search(db, "Motadata platform overview architecture differentiators", allowed, top_k=8)
    user = (f"<placeholders>{json.dumps(t.placeholders)}</placeholders>\n"
            f"<workspace_material>\n{json.dumps(runs, default=str)[:200000]}\n"
            f"<compliance_answers>\n{compliance_digest(db, ws)[:200000]}\n</compliance_answers>\n</workspace_material>\n"
            f"<knowledge>\n{retrieval.format_hits(hits)}\n</knowledge>\n{sample_text}")
    ctx.progress(20, "Writing proposal content")
    out = ai.call(db, "proposal_generation", system=A.PROPOSAL_SYSTEM, user=user, schema=A.PROPOSAL_SCHEMA,
                  user_id=job.created_by, ref_type="rfp_workspace", ref_id=ws.id, job_id=job.id)
    content = {s["placeholder"]: s["content"] for s in out["sections"]}
    n = (db.scalar(select(func.max(RFPProposal.version)).where(RFPProposal.workspace_id == ws.id)) or 0) + 1
    db.add(RFPProposal(workspace_id=ws.id, template_id=t.id, version=n, content=content, created_by=job.created_by))
    db.commit()
    return {"version": n}


@router.get("/workspaces/{wid}/proposals")
def proposals(wid: int, cu: CurrentUser = Depends(require("rfp.view")), db: Session = Depends(get_db)):
    return [{"id": p.id, "version": p.version, "template_id": p.template_id, "content": p.content, "updated_at": p.updated_at}
            for p in db.scalars(select(RFPProposal).where(RFPProposal.workspace_id == wid).order_by(RFPProposal.version.desc()))]


@router.put("/proposals/{pid}")
def edit_proposal(pid: int, body: dict, cu: CurrentUser = Depends(require("rfp.edit")), db: Session = Depends(get_db)):
    p = db.get(RFPProposal, pid) or _404()
    p.content = body.get("content") or p.content
    audit(db, cu.user, "rfp.proposal_edited", "rfp_proposal", pid, version=p.version)
    db.commit()
    return {"ok": True}


@router.get("/proposals/{pid}/export")
def export_proposal(pid: int, fmt: str = "docx", cu: CurrentUser = Depends(require("rfp.export")), db: Session = Depends(get_db)):
    p = db.get(RFPProposal, pid) or _404()
    t = db.get(RFPTemplate, p.template_id)
    data = fill(read_file(db.get(StoredFile, t.file_id)), p.content)
    ws = db.get(RFPWorkspace, p.workspace_id)
    mime = DOCX
    if fmt == "pdf":
        data, mime = docx_to_pdf(data), "application/pdf"
    audit(db, cu.user, "rfp.proposal_exported", "rfp_proposal", pid, version=p.version, format=fmt)
    db.commit()
    return Response(data, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="Technical Proposal - {_safe(ws.name)} - v{p.version}.{fmt}"'})


@router.get("/workspaces/{wid}/export")
def export(wid: int, kind: str = "compliance", cu: CurrentUser = Depends(require("rfp.export")), db: Session = Depends(get_db)):
    ws = _ws(db, wid)
    rows = db.execute(select(RFPRequirement, RFPComplianceResponse)
                      .outerjoin(RFPComplianceResponse, RFPComplianceResponse.requirement_id == RFPRequirement.id)
                      .where(RFPRequirement.workspace_id == wid, RFPRequirement.active.is_(True)).order_by(RFPRequirement.id)).all()
    if kind == "compliance":
        data, mime, name = exports.compliance_sheet(ws.name, rows), XLSX, f"Compliance - {_safe(ws.name)}.xlsx"
    elif kind == "internal":
        data, mime, name = exports.internal_workbook(ws.name, rows, _latest_runs(db, wid)), XLSX, f"RFP workspace - {_safe(ws.name)}.xlsx"
    elif kind in ("report", "report_pdf"):
        data, mime = exports.report_docx(ws.name, _latest_runs(db, wid)), DOCX
        name = f"RFP analysis - {_safe(ws.name)}.docx"
        if kind == "report_pdf":
            data, mime, name = docx_to_pdf(data), "application/pdf", name.replace(".docx", ".pdf")
    elif kind == "hw_sizing":
        sizing = (_latest_runs(db, wid).get("architecture") or {}).get("motadata_sizing")
        if not sizing:
            raise HTTPException(400, "Run the architecture and sizing agent first")
        data, mime, name = exports.hw_sizing_workbook(ws.name, sizing), XLSX, f"HW sizing - {_safe(ws.name)}.xlsx"
    elif kind == "scope":
        scope = _latest_runs(db, wid).get("scope")
        if not scope:
            raise HTTPException(400, "Run the Motadata scope agent first")
        data, mime, name = exports.scope_workbook(ws.name, rows, scope), XLSX, f"Scope matrix - {_safe(ws.name)}.xlsx"
    elif kind in ("prebid", "prebid_docx"):
        prebid = _latest_runs(db, wid).get("prebid")
        if not prebid or not prebid.get("queries"):
            raise HTTPException(400, "Run the pre-bid query agent first")
        if kind == "prebid":
            data, mime, name = exports.prebid_sheet(ws.name, prebid), XLSX, f"Pre-bid queries - {_safe(ws.name)}.xlsx"
        else:
            data, mime, name = exports.prebid_docx(ws.name, prebid), DOCX, f"Pre-bid queries - {_safe(ws.name)}.docx"
    else:
        raise HTTPException(400, "Unknown export")
    audit(db, cu.user, "rfp.exported", "rfp_workspace", wid, kind=kind)
    db.commit()
    return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------- submission ----------
@router.post("/workspaces/{wid}/submit")
def submit(wid: int, cu: CurrentUser = Depends(require("rfp.approve")), db: Session = Depends(get_db)):
    ws = _ws(db, wid)
    if ws.status == "Submitted":
        raise HTTPException(400, "Already submitted")
    rows = db.execute(select(RFPRequirement, RFPComplianceResponse)
                      .join(RFPComplianceResponse, RFPComplianceResponse.requirement_id == RFPRequirement.id)
                      .where(RFPRequirement.workspace_id == wid, RFPRequirement.active.is_(True),
                             RFPComplianceResponse.approved.is_(True))).all()
    c = db.get(CustomerContext, ws.customer_id) if ws.customer_id else None
    sub_docs = db.scalars(select(RFPDocument).where(RFPDocument.workspace_id == wid)).all()
    sr = SubmittedRFP(customer=c.name if c else ws.name, industry=c.industry if c else "", submitted_on=date.today(),
                      product_version=ws.product_version, title=ws.name, workspace_id=ws.id, created_by=cu.id,
                      file_ids=[{"file_id": d.file_id, "name": d.name, "role": d.role} for d in sub_docs])
    db.add(sr)
    db.flush()
    n = add_pairs(db, sr.id, [{"requirement": r.text, "status": a.status, "response": a.response,
                               "reference": f"{r.number} {r.source_ref}"} for r, a in rows])
    ws.status, ws.submitted_at = "Submitted", utcnow()
    audit(db, cu.user, "rfp.submitted", "rfp_workspace", wid, pairs=n, submitted_rfp=sr.id)
    db.commit()
    return {"submitted_rfp_id": sr.id, "pairs": n}


def _safe(s: str) -> str:
    return "".join(ch for ch in s if ch.isalnum() or ch in " -_").strip() or "workspace"


def _404():
    raise HTTPException(404, "Not found")
