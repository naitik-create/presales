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
from app.modules.rfp import bidparams, boq_client, chat, exports, hwsizing, stages, workflow
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
    """Save an edit as a new version, so earlier versions stay available."""
    run = db.get(RFPAgentRun, run_id) or _404()
    if not isinstance(body.get("output"), dict):
        raise HTTPException(400, "output must be an object")
    ws = _ws(db, run.workspace_id)
    new = stages.new_version(db, ws, run.agent_key, body["output"], "edited")
    if run.agent_key in workflow.STAGE_OF_AGENT:
        stage = workflow.STAGE_OF_AGENT[run.agent_key]
        stages.changed(db, ws, stage, f"{workflow.BY_KEY[stage]['label']} was edited by {_who(cu)}")
    audit(db, cu.user, "rfp.agent_output_edited", "rfp_agent_run", new.id, agent=run.agent_key, previous=run_id)
    db.commit()
    return {"ok": True, "id": new.id}


@router.post("/agent-runs/{run_id}/approve")
def approve_agent_output(run_id: int, cu: CurrentUser = Depends(require("rfp.approve")), db: Session = Depends(get_db)):
    run = db.get(RFPAgentRun, run_id) or _404()
    if run.agent_key in workflow.STAGE_OF_AGENT:  # review steps are approved in order on the Bid workflow tab
        try:
            stages.approve(db, _ws(db, run.workspace_id), workflow.STAGE_OF_AGENT[run.agent_key], _who(cu), cu.id)
        except ValueError as e:
            raise HTTPException(400, str(e))
    else:
        run.approved = True
    audit(db, cu.user, "rfp.agent_output_approved", "rfp_agent_run", run_id, agent=run.agent_key)
    db.commit()
    return {"ok": True}


# ---------- guided bid workflow: review, edit, revise with AI, approve, then download ----------
def _who(cu: CurrentUser) -> str:
    return cu.user.full_name or cu.user.username


def _stage(key: str) -> dict:
    if key not in workflow.BY_KEY:
        raise HTTPException(404, "Unknown step")
    return workflow.BY_KEY[key]


@router.get("/workspaces/{wid}/workflow")
def get_workflow(wid: int, cu: CurrentUser = Depends(require("rfp.view")), db: Session = Depends(get_db)):
    return stages.overview(db, _ws(db, wid))


@router.put("/workspaces/{wid}/stages/{key}")
def edit_stage(wid: int, key: str, body: dict, cu: CurrentUser = Depends(require("rfp.edit")), db: Session = Depends(get_db)):
    """Direct edit on the review screen; saved as a new version that needs approving again."""
    ws, s = _ws(db, wid), _stage(key)
    if key not in workflow.DOC_STAGES:
        raise HTTPException(400, "This step is edited in place (answers, bid parameters)")
    run = stages.latest(db, wid, s["agent"])
    if not run:
        raise HTTPException(400, f"{s['label']} has not been generated yet")
    if not isinstance(body.get("output"), dict):
        raise HTTPException(400, "output must be an object")
    new = stages.new_version(db, ws, s["agent"], workflow.clean_edit(key, stages.content(run), body["output"]), "edited")
    stages.changed(db, ws, key, f"{s['label']} was edited by {_who(cu)}")
    audit(db, cu.user, "rfp.stage_edited", "rfp_workspace", wid, stage=key, run_id=new.id)
    db.commit()
    return stages.overview(db, ws)


class ReviseIn(BaseModel):
    instruction: str
    requirement_ids: list[int] = []


@router.post("/workspaces/{wid}/stages/{key}/revise")
def revise_stage(wid: int, key: str, body: ReviseIn, cu: CurrentUser = Depends(require("rfp.edit")),
                 db: Session = Depends(get_db)):
    """Ask the AI to change this step; the result comes back as a draft to accept or discard."""
    ws, s = _ws(db, wid), _stage(key)
    if key not in workflow.REVISABLE:
        raise HTTPException(400, f"{s['label']} is edited directly")
    instruction = body.instruction.strip()
    if len(instruction) < 3:
        raise HTTPException(400, "Say what should change")
    if key == "compliance":
        if not body.requirement_ids:
            raise HTTPException(400, "Select the requirements to revise")
        if len(body.requirement_ids) > stages.MAX_COMPLIANCE_REVISE:
            raise HTTPException(400, f"Revise at most {stages.MAX_COMPLIANCE_REVISE} requirements at a time")
    elif not stages.latest(db, wid, s["agent"]):
        raise HTTPException(400, f"{s['label']} has not been generated yet")
    job = _enqueue_rfp(db, "rfp.revise", ws, cu, stage=key, instruction=instruction[:4000],
                       requirement_ids=body.requirement_ids, by=_who(cu))
    audit(db, cu.user, "rfp.stage_revise_requested", "rfp_workspace", wid, stage=key, instruction=instruction[:500])
    db.commit()
    return {"job_id": job.id}


@router.post("/workspaces/{wid}/stages/{key}/draft/accept")
def accept_draft(wid: int, key: str, cu: CurrentUser = Depends(require("rfp.edit")), db: Session = Depends(get_db)):
    ws, s = _ws(db, wid), _stage(key)
    draft = stages.latest(db, wid, workflow.DRAFT_PREFIX + key) or _404()
    skipped = 0
    if key == "compliance":
        for a in draft.output.get("answers") or []:
            c = db.scalar(select(RFPComplianceResponse).where(RFPComplianceResponse.requirement_id == a["requirement_id"]))
            if c is None:
                c = RFPComplianceResponse(requirement_id=a["requirement_id"])
                db.add(c)
            elif c.approved and not cu.has("rfp.approve"):
                skipped += 1
                continue
            for k, v in a["after"].items():
                setattr(c, k, v)
            c.approved, c.approved_by, c.approved_at = False, None, None
    else:
        run = stages.latest(db, wid, s["agent"])
        if not run or run.id != draft.output.get("base_run_id"):
            raise HTTPException(409, f"{s['label']} changed after this revision was made. Discard it and ask again.")
        stages.new_version(db, ws, s["agent"], draft.output["proposal"], "revised")
        stages.changed(db, ws, key, f"{s['label']} was revised ({_who(cu)}: {draft.output.get('instruction', '')[:120]})")
    chat.close_by_job(db, wid, draft.job_id, "applied")
    db.delete(draft)
    audit(db, cu.user, "rfp.stage_revision_accepted", "rfp_workspace", wid, stage=key, skipped=skipped)
    db.commit()
    return {**stages.overview(db, ws), "skipped": skipped}


@router.post("/workspaces/{wid}/stages/{key}/draft/discard")
def discard_draft(wid: int, key: str, cu: CurrentUser = Depends(require("rfp.edit")), db: Session = Depends(get_db)):
    ws = _ws(db, wid)
    _stage(key)
    d = stages.drop_draft(db, wid, key)
    if d:
        chat.close_by_job(db, wid, d.job_id, "discarded")
    audit(db, cu.user, "rfp.stage_revision_discarded", "rfp_workspace", wid, stage=key)
    db.commit()
    return stages.overview(db, ws)


@router.post("/workspaces/{wid}/stages/{key}/approve")
def approve_stage(wid: int, key: str, body: dict | None = None, cu: CurrentUser = Depends(require("rfp.approve")),
                  db: Session = Depends(get_db)):
    """{"approved": true} approves the step and opens its downloads; false reopens it (and the approved steps built
    on it are marked as needing review)."""
    ws = _ws(db, wid)
    _stage(key)
    approved = (body or {}).get("approved", True)
    try:
        if approved:
            stages.approve(db, ws, key, _who(cu), cu.id)
        else:
            stages.reopen(db, ws, key, _who(cu))
    except ValueError as e:
        raise HTTPException(400, str(e))
    audit(db, cu.user, "rfp.stage_approved" if approved else "rfp.stage_reopened", "rfp_workspace", wid, stage=key)
    db.commit()
    return stages.overview(db, ws)


@router.get("/workspaces/{wid}/stages/{key}/versions")
def stage_versions(wid: int, key: str, cu: CurrentUser = Depends(require("rfp.view")), db: Session = Depends(get_db)):
    _ws(db, wid)
    s = _stage(key)
    return stages.versions(db, wid, s["agent"]) if s["agent"] else []


@router.post("/workspaces/{wid}/stages/{key}/versions/{run_id}/restore")
def restore_version(wid: int, key: str, run_id: int, cu: CurrentUser = Depends(require("rfp.edit")),
                    db: Session = Depends(get_db)):
    ws, s = _ws(db, wid), _stage(key)
    old = db.get(RFPAgentRun, run_id)
    if not old or old.workspace_id != wid or old.agent_key != s["agent"] or key not in workflow.DOC_STAGES:
        raise HTTPException(404, "Version not found")
    stages.new_version(db, ws, s["agent"], stages.content(old), "restored")
    stages.changed(db, ws, key, f"{s['label']}: an earlier version was restored by {_who(cu)}")
    audit(db, cu.user, "rfp.stage_version_restored", "rfp_workspace", wid, stage=key, run_id=run_id)
    db.commit()
    return stages.overview(db, ws)


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


# ---------- bid parameters (review, confirm) and unpriced BOQs ----------
BID_PARAMS = "bid_parameters"  # stored as an RFPAgentRun row: output = parameters, approved = confirmed


def _params_run(db: Session, wid: int) -> RFPAgentRun | None:
    return db.scalar(select(RFPAgentRun).where(RFPAgentRun.workspace_id == wid, RFPAgentRun.agent_key == BID_PARAMS)
                     .order_by(RFPAgentRun.id.desc()))


def _prefilled(db: Session, ws: RFPWorkspace) -> dict:
    runs = _latest_runs(db, ws.id)
    customer = db.get(CustomerContext, ws.customer_id).name if ws.customer_id else ""
    arch = runs.get("architecture") or {}
    inputs = (arch.get("motadata_sizing") or {}).get("inputs") or hwsizing.clean_inputs(arch.get("motadata_inputs") or [])
    return bidparams.prefill(customer=customer, products=ws.products or [], analysis=runs.get("analysis") or {},
                             scope=runs.get("scope") or {}, sizing_inputs=inputs)


def _params_out(db: Session, ws: RFPWorkspace, run: RFPAgentRun | None) -> dict:
    data = run.output if run else {**_prefilled(db, ws), "sizing": None}
    if data.get("sizing") is None:
        data = {**data, "sizing": bidparams.compute_sizing(data["params"], data["sizing_inputs"])}
    boq_hints = (_latest_runs(db, ws.id).get("boq") or {}).get("lines", [])
    return {**data, "saved": run is not None, "confirmed": bool(run and run.approved),
            "confirmed_at": run.at if run and run.approved else None, "fields": bidparams.fields_meta(),
            "sizing_fields": [{"name": k, "label": v[0], "product": v[1]} for k, v in hwsizing.INPUTS.items()],
            "warnings": bidparams.warnings(data["params"]), "boq_hints": boq_hints}


@router.get("/workspaces/{wid}/bid-parameters")
def get_bid_parameters(wid: int, cu: CurrentUser = Depends(require("rfp.view")), db: Session = Depends(get_db)):
    ws = _ws(db, wid)
    return _params_out(db, ws, _params_run(db, wid))


@router.put("/workspaces/{wid}/bid-parameters")
def save_bid_parameters(wid: int, body: dict, cu: CurrentUser = Depends(require("rfp.edit")), db: Session = Depends(get_db)):
    """Save edited parameters and sizing inputs as a new version; it needs confirming again."""
    ws = _ws(db, wid)
    run = _save_params(db, ws, body.get("params") or {}, body.get("sizing_inputs"), f"Edited by {_who(cu)}")
    audit(db, cu.user, "rfp.bid_parameters_saved", "rfp_workspace", wid)
    db.commit()
    return _params_out(db, ws, run)


def _save_params(db: Session, ws: RFPWorkspace, changes: dict, sizing_inputs: list | None, source: str) -> RFPAgentRun:
    """New, unconfirmed version of the bid parameters. sizing_inputs None keeps the current ones."""
    current = _params_run(db, ws.id)
    base = current.output if current else _prefilled(db, ws)
    try:
        params = bidparams.clean({**base["params"], **changes})
        items = []
        for i in (base["sizing_inputs"] if sizing_inputs is None else sizing_inputs) or []:
            if i.get("name") in hwsizing.INPUTS and str(i.get("value", "")).strip() != "":
                items.append({"name": i["name"], "value": float(i["value"]), "ref": str(i.get("ref", ""))[:200],
                              "note": str(i.get("note", ""))[:300]})
    except (TypeError, ValueError) as e:
        raise HTTPException(400, str(e) if str(e) else "Check the values entered")
    sources = dict(base.get("sources") or {})
    for k, v in params.items():
        if base["params"].get(k) != v:
            sources[k] = source
    out = {"params": params, "sources": sources, "notes": base.get("notes", []), "sizing_inputs": items,
           "sizing": bidparams.compute_sizing(params, items)}
    run = RFPAgentRun(workspace_id=ws.id, agent_key=BID_PARAMS, revision=ws.revision, output=out, approved=False)
    db.add(run)
    db.flush()
    return run


@router.post("/workspaces/{wid}/bid-parameters/confirm")
def confirm_bid_parameters(wid: int, body: dict | None = None, cu: CurrentUser = Depends(require("rfp.approve")),
                           db: Session = Depends(get_db)):
    """Confirming the bid parameters is approving the Sizing and BOQ step of the bid workflow."""
    ws = _ws(db, wid)
    run = _params_run(db, wid)
    if not run:
        raise HTTPException(400, "Save the bid parameters first")
    confirm = (body or {}).get("confirmed", True)
    try:
        if confirm:
            stages.approve(db, ws, "boq", _who(cu), cu.id)
        else:
            stages.reopen(db, ws, "boq", _who(cu))
    except ValueError as e:
        raise HTTPException(400, str(e))
    audit(db, cu.user, "rfp.bid_parameters_confirmed" if confirm else "rfp.bid_parameters_unlocked", "rfp_workspace", wid)
    db.commit()
    return _params_out(db, ws, run)


def _confirmed_params(db: Session, wid: int) -> dict:
    run = _params_run(db, wid)
    if not run or not run.approved:
        raise HTTPException(400, "Confirm the bid parameters first (Bid parameters tab)")
    return run.output


BID_PACK = "bid_pack"  # RFPAgentRun row per generated pack: output = {file_id, files, params_run_id, by}


def _pack_out(run: RFPAgentRun) -> dict:
    return {"id": run.id, "at": run.at, **{k: run.output.get(k) for k in ("files", "by", "file_name", "size")}}


@router.post("/workspaces/{wid}/bid-pack")
def make_bid_pack(wid: int, cu: CurrentUser = Depends(require("rfp.export")), db: Session = Depends(get_db)):
    """The approved steps' downloads in one versioned ZIP; steps not approved yet are listed, not included. No prices."""
    ws = _ws(db, wid)
    approved = {s["key"] for s in workflow.STAGES if stages.is_approved(db, wid, s["key"])}
    if not approved:
        raise HTTPException(400, "Approve at least one step of the bid workflow first")
    rows = db.execute(select(RFPRequirement, RFPComplianceResponse)
                      .outerjoin(RFPComplianceResponse, RFPComplianceResponse.requirement_id == RFPRequirement.id)
                      .where(RFPRequirement.workspace_id == wid, RFPRequirement.active.is_(True)).order_by(RFPRequirement.id)).all()
    bp_run = _params_run(db, wid)
    bp = bp_run.output if bp_run and bp_run.approved else None
    data, files = exports.bid_pack(ws.name, rows, _latest_runs(db, wid), bp,
                                   lambda: boq_client.unpriced_boq(bidparams.boq_request(bp["params"])), approved)
    n = (db.scalar(select(func.count()).select_from(RFPAgentRun)
                   .where(RFPAgentRun.workspace_id == wid, RFPAgentRun.agent_key == BID_PACK)) or 0) + 1
    name = f"Bid pack v{n} - {_safe((bp or {}).get('params', {}).get('customer_name') or ws.name)}.zip"
    f = save_file(db, data, name, "rfp_bidpack", cu.id, "application/zip", allowed={".zip"})
    run = RFPAgentRun(workspace_id=wid, agent_key=BID_PACK, revision=ws.revision, approved=True,
                      output={"file_id": f.id, "file_name": f.original_name, "size": len(data), "files": files,
                              "params_run_id": bp_run.id if bp else None, "by": _who(cu)})
    db.add(run)
    audit(db, cu.user, "rfp.bid_pack_generated", "rfp_workspace", wid, file_id=f.id,
          included=sum(1 for x in files if x["included"]), skipped=sum(1 for x in files if not x["included"]))
    db.commit()
    return _pack_out(run)


@router.get("/workspaces/{wid}/bid-packs")
def list_bid_packs(wid: int, cu: CurrentUser = Depends(require("rfp.view")), db: Session = Depends(get_db)):
    _ws(db, wid)
    runs = db.scalars(select(RFPAgentRun).where(RFPAgentRun.workspace_id == wid, RFPAgentRun.agent_key == BID_PACK)
                      .order_by(RFPAgentRun.id.desc()).limit(50)).all()
    return [_pack_out(r) for r in runs]


@router.get("/bid-packs/{run_id}/download")
def download_bid_pack(run_id: int, cu: CurrentUser = Depends(require("rfp.export")), db: Session = Depends(get_db)):
    run = db.get(RFPAgentRun, run_id)
    if not run or run.agent_key != BID_PACK:
        raise HTTPException(404, "Not found")
    f = db.get(StoredFile, run.output["file_id"])
    audit(db, cu.user, "rfp.bid_pack_downloaded", "rfp_workspace", run.workspace_id, file_id=f.id)
    db.commit()
    return Response(read_file(f), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{f.original_name}"'})


def _latest_runs(db: Session, wid: int) -> dict:
    out = {}
    for key in A.DOC_AGENTS:
        run = db.scalar(select(RFPAgentRun).where(RFPAgentRun.workspace_id == wid, RFPAgentRun.agent_key == key)
                        .order_by(RFPAgentRun.id.desc()))
        if run:
            out[key] = run.edited_output or run.output
    return out


# ---------- chat about this RFP ----------
@router.get("/workspaces/{wid}/chat")
def chat_messages(wid: int, cu: CurrentUser = Depends(require("rfp.view")), db: Session = Depends(get_db)):
    _ws(db, wid)
    return [chat.message_out(db, m) for m in chat.messages(db, wid)]


class ChatIn(BaseModel):
    question: str


@router.post("/workspaces/{wid}/chat")
def chat_ask(wid: int, body: ChatIn, cu: CurrentUser = Depends(require("rfp.view")), db: Session = Depends(get_db)):
    """Answer a question about this RFP, or propose changes the team can apply. A proposed change to a review step is
    prepared straight away (as a draft on that step) when the user may edit and no job is running."""
    ws = _ws(db, wid)
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "Type a question")
    params = _params_out(db, ws, _params_run(db, wid))
    try:
        run = chat.ask(db, ws, question=question[:4000], user_id=cu.id, by=_who(cu), sections=cu.section_keys(),
                       runs=_latest_runs(db, wid), params=params)
    except ai.AIError as e:
        raise HTTPException(502, str(e)) from e
    audit(db, cu.user, "rfp.chat_asked", "rfp_workspace", wid, actions=len(run.output.get("actions") or []))
    db.commit()
    if cu.has("rfp.edit"):
        for i, a in enumerate(run.output.get("actions") or []):
            if a["kind"] == "revise" and a["state"] == "proposed":
                try:
                    _prepare(db, ws, cu, run, i)
                except HTTPException:
                    pass  # a job is already running: the card offers Prepare
                break
    return chat.message_out(db, run)


def _chat_action(db: Session, wid: int, mid: int, index: int) -> tuple[RFPAgentRun, dict]:
    run = db.get(RFPAgentRun, mid)
    if not run or run.workspace_id != wid or run.agent_key != chat.CHAT_KEY:
        raise HTTPException(404, "Message not found")
    actions = run.output.get("actions") or []
    if index < 0 or index >= len(actions):
        raise HTTPException(404, "Proposed change not found")
    return run, actions[index]


def _prepare(db: Session, ws: RFPWorkspace, cu: CurrentUser, run: RFPAgentRun, index: int) -> None:
    a = run.output["actions"][index]
    job = _enqueue_rfp(db, "rfp.revise", ws, cu, stage=a["stage"], instruction=a["instruction"],
                       requirement_ids=a.get("requirement_ids") or [], by=_who(cu))
    chat.set_action(run, index, state="preparing", job_id=job.id)
    audit(db, cu.user, "rfp.chat_change_prepared", "rfp_workspace", ws.id, stage=a["stage"], job_id=job.id)
    db.commit()


@router.post("/workspaces/{wid}/chat/{mid}/actions/{index}/prepare")
def chat_prepare(wid: int, mid: int, index: int, cu: CurrentUser = Depends(require("rfp.edit")), db: Session = Depends(get_db)):
    ws = _ws(db, wid)
    run, a = _chat_action(db, wid, mid, index)
    now = chat.message_out(db, run)["actions"][index]
    if a["kind"] != "revise" or not (now["state"] in ("proposed", "failed", "closed")
                                     or (now["state"] == "ready" and now.get("outdated"))):
        raise HTTPException(400, "This change cannot be prepared")
    _prepare(db, ws, cu, run, index)
    return chat.message_out(db, run)


@router.post("/workspaces/{wid}/chat/{mid}/actions/{index}/apply")
def chat_apply(wid: int, mid: int, index: int, cu: CurrentUser = Depends(require("rfp.edit")), db: Session = Depends(get_db)):
    """Apply a proposed change. A step change goes through its draft (the same as Accept on the step); a bid parameter
    change saves a new, unconfirmed version of the bid parameters."""
    ws = _ws(db, wid)
    run, a = _chat_action(db, wid, mid, index)
    if a["kind"] == "params":
        if a["state"] != "proposed":
            raise HTTPException(400, "This change was already handled")
        # only the fields the chat changed, on top of the parameters as they are now
        changes = {p["name"]: p["after"] for p in a.get("preview") or [] if p.get("target") == "param"}
        new_sizing = {p["name"]: p["after"] for p in a.get("preview") or [] if p.get("target") == "sizing"}
        sizing = []
        for i in _params_out(db, ws, _params_run(db, wid)).get("sizing_inputs") or []:
            if i["name"] in new_sizing:
                i = {**i, "value": new_sizing.pop(i["name"]), "ref": "Changed in chat", "note": ""}
            sizing.append(i)
        sizing += [{"name": k, "value": v, "ref": "Changed in chat", "note": ""} for k, v in new_sizing.items() if v != ""]
        _save_params(db, ws, changes, sizing, f"Changed in chat by {_who(cu)}")
        chat.set_action(run, index, state="applied")
        audit(db, cu.user, "rfp.chat_change_applied", "rfp_workspace", wid, stage="boq")
        db.commit()
        return chat.message_out(db, run)
    out = chat.message_out(db, run)["actions"][index]
    if out["state"] != "ready":
        raise HTTPException(400, "The change is not ready yet")
    accept_draft(wid, a["stage"], cu, db)
    db.refresh(run)
    return chat.message_out(db, run)


@router.post("/workspaces/{wid}/chat/{mid}/actions/{index}/discard")
def chat_discard(wid: int, mid: int, index: int, cu: CurrentUser = Depends(require("rfp.edit")), db: Session = Depends(get_db)):
    _ws(db, wid)
    run, a = _chat_action(db, wid, mid, index)
    out = chat.message_out(db, run)["actions"][index]
    if out["state"] == "ready":
        discard_draft(wid, a["stage"], cu, db)
        db.refresh(run)
    else:
        chat.set_action(run, index, state="discarded")
        db.commit()
    return chat.message_out(db, run)


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
    blocked = stages.export_blocked(db, wid, kind)
    if blocked:
        raise HTTPException(400, blocked)
    rows = db.execute(select(RFPRequirement, RFPComplianceResponse)
                      .outerjoin(RFPComplianceResponse, RFPComplianceResponse.requirement_id == RFPRequirement.id)
                      .where(RFPRequirement.workspace_id == wid, RFPRequirement.active.is_(True)).order_by(RFPRequirement.id)).all()
    if kind == "synopsis":
        analysis = _latest_runs(db, wid).get("analysis") or {}
        data, mime, name = exports.synopsis_docx(ws.name, analysis), DOCX, f"Synopsis - {_safe(ws.name)}.docx"
    elif kind == "considerations":
        cons = _latest_runs(db, wid).get("considerations") or {}
        data, mime, name = exports.considerations_docx(ws.name, cons), DOCX, f"Key considerations - {_safe(ws.name)}.docx"
    elif kind == "considerations_text":
        cons = _latest_runs(db, wid).get("considerations") or {}
        return {"text": workflow.considerations_text(ws.name, cons)}
    elif kind == "compliance":
        data, mime, name = exports.compliance_sheet(ws.name, rows), XLSX, f"Compliance - {_safe(ws.name)}.xlsx"
    elif kind == "internal":
        data, mime, name = exports.internal_workbook(ws.name, rows, _latest_runs(db, wid)), XLSX, f"RFP workspace - {_safe(ws.name)}.xlsx"
    elif kind in ("report", "report_pdf"):
        data, mime = exports.report_docx(ws.name, _latest_runs(db, wid)), DOCX
        name = f"RFP analysis - {_safe(ws.name)}.docx"
        if kind == "report_pdf":
            data, mime, name = docx_to_pdf(data), "application/pdf", name.replace(".docx", ".pdf")
    elif kind == "sw_boq":
        p = _confirmed_params(db, wid)["params"]
        try:
            data = boq_client.unpriced_boq(bidparams.boq_request(p))
        except boq_client.BoqError as e:
            raise HTTPException(502, str(e))
        mime, name = XLSX, f"Unpriced SW BOQ - {_safe(p['customer_name'] or ws.name)}.xlsx"
    elif kind == "hw_boq":
        bp = _confirmed_params(db, wid)
        if not bp["sizing"].get("sites"):
            raise HTTPException(400, bp["sizing"].get("error") or "No hardware sizing for these parameters")
        data, mime = exports.hw_boq_workbook(ws.name, bp["params"], bp["sizing"]), XLSX
        name = f"Unpriced HW BOQ - {_safe(bp['params']['customer_name'] or ws.name)}.xlsx"
    elif kind == "hw_sizing":
        bp_run = _params_run(db, wid)
        sizing = bp_run.output["sizing"] if bp_run and bp_run.approved else \
            (_latest_runs(db, wid).get("architecture") or {}).get("motadata_sizing")
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
