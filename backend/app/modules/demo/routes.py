from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.deps import CurrentUser, require
from app.core.jobs import enqueue
from app.db import get_db
from app.models.core import CustomerContext, Job
from app.models.demo import DemoProject, DemoScriptVersion, DemoTemplate, DemoUseCase
from app.modules.demo.service import script_docx, use_case_out, verify_steps
from app.parsing.extract import docx_to_pdf

router = APIRouter(prefix="/demo", tags=["demo"])


# ---------- use-case library ----------
class UseCaseIn(BaseModel):
    name: str
    product: str
    module_key: str
    pain: str = ""
    industries: list[str] = []
    navigation: list[str] = []
    what_to_show: str = ""
    expected_result: str = ""
    talk_track: str = ""
    value_statement: str = ""
    differentiator: str = ""
    objections: list[dict] = []
    prerequisites: str = ""
    minutes: int = 10


@router.get("/use-cases")
def list_use_cases(cu: CurrentUser = Depends(require("usecases.view", "demo.view")), db: Session = Depends(get_db)):
    return [use_case_out(u) for u in db.scalars(select(DemoUseCase).order_by(DemoUseCase.product, DemoUseCase.name))]


@router.post("/use-cases")
def create_use_case(body: UseCaseIn, cu: CurrentUser = Depends(require("usecases.create")), db: Session = Depends(get_db)):
    u = DemoUseCase(**body.model_dump(), created_by=cu.id)
    db.add(u)
    db.flush()
    audit(db, cu.user, "usecase.created", "use_case", u.id, name=u.name)
    db.commit()
    return use_case_out(u)


@router.put("/use-cases/{uid}")
def update_use_case(uid: int, body: UseCaseIn, cu: CurrentUser = Depends(require("usecases.edit")), db: Session = Depends(get_db)):
    u = db.get(DemoUseCase, uid) or _404()
    for k, v in body.model_dump().items():
        setattr(u, k, v)
    u.status = "Draft"  # an edited use case needs approval again
    audit(db, cu.user, "usecase.updated", "use_case", u.id, name=u.name)
    db.commit()
    return use_case_out(u)


@router.post("/use-cases/{uid}/approve")
def approve_use_case(uid: int, cu: CurrentUser = Depends(require("usecases.approve")), db: Session = Depends(get_db)):
    u = db.get(DemoUseCase, uid) or _404()
    u.status, u.approved_by = "Approved", cu.id
    audit(db, cu.user, "usecase.approved", "use_case", u.id, name=u.name)
    db.commit()
    return use_case_out(u)


# ---------- projects & scripts ----------
class ProjectIn(BaseModel):
    title: str
    customer_id: int | None = None
    inputs: dict = {}


@router.get("/projects")
def list_projects(cu: CurrentUser = Depends(require("demo.view")), db: Session = Depends(get_db)):
    rows = db.execute(select(DemoProject, CustomerContext.name).outerjoin(CustomerContext, CustomerContext.id == DemoProject.customer_id)
                      .order_by(DemoProject.updated_at.desc()).limit(300)).all()
    return [{"id": p.id, "title": p.title, "customer": n or "", "customer_id": p.customer_id, "current_version": p.current_version,
             "outcome": p.outcome, "updated_at": p.updated_at} for p, n in rows]


@router.post("/projects")
def create_project(body: ProjectIn, cu: CurrentUser = Depends(require("demo.create")), db: Session = Depends(get_db)):
    p = DemoProject(**body.model_dump(), created_by=cu.id)
    db.add(p)
    db.flush()
    audit(db, cu.user, "demo.project_created", "demo_project", p.id, title=p.title)
    db.commit()
    return {"id": p.id}


@router.get("/projects/{pid}")
def get_project(pid: int, version: int | None = None, cu: CurrentUser = Depends(require("demo.view")), db: Session = Depends(get_db)):
    p = db.get(DemoProject, pid) or _404()
    v = db.scalar(select(DemoScriptVersion).where(DemoScriptVersion.project_id == pid,
                                                  DemoScriptVersion.version == (version or p.current_version)))
    versions = db.scalars(select(DemoScriptVersion.version).where(DemoScriptVersion.project_id == pid)
                          .order_by(DemoScriptVersion.version.desc())).all()
    job = db.scalar(select(Job).where(Job.ref_type == "demo_project", Job.ref_id == pid).order_by(Job.id.desc()))
    return {"id": p.id, "title": p.title, "customer_id": p.customer_id, "inputs": p.inputs, "outcome": p.outcome,
            "current_version": p.current_version, "versions": versions,
            "script": {"version": v.version, "content": v.content, "unverified_steps": v.unverified_steps, "origin": v.origin,
                       "at": v.at} if v else None,
            "job": {"id": job.id, "status": job.status, "progress": job.progress, "message": job.message,
                    "error": job.error.split("\n")[0] if job.error else ""} if job else None}


@router.put("/projects/{pid}")
def update_project(pid: int, body: ProjectIn, cu: CurrentUser = Depends(require("demo.edit")), db: Session = Depends(get_db)):
    p = db.get(DemoProject, pid) or _404()
    p.title, p.customer_id, p.inputs = body.title, body.customer_id, body.inputs
    db.commit()
    return {"ok": True}


@router.post("/projects/{pid}/generate")
def generate(pid: int, cu: CurrentUser = Depends(require("demo.create", "demo.edit")), db: Session = Depends(get_db)):
    p = db.get(DemoProject, pid) or _404()
    if not db.scalar(select(func.count()).select_from(DemoUseCase).where(DemoUseCase.status == "Approved")):
        raise HTTPException(400, "The demo use-case library has no approved use cases yet")
    job = enqueue(db, "demo.generate", {"project_id": p.id}, user_id=cu.id, ref_type="demo_project", ref_id=p.id)
    audit(db, cu.user, "demo.generate", "demo_project", p.id)
    db.commit()
    return {"job_id": job.id}


@router.post("/projects/{pid}/versions")
def save_script(pid: int, body: dict, cu: CurrentUser = Depends(require("demo.edit")), db: Session = Depends(get_db)):
    p = db.get(DemoProject, pid) or _404()
    content = body.get("content") or {}
    library = {str(u.id): u for u in db.scalars(select(DemoUseCase))}
    flags = verify_steps(content, library, "")
    n = (db.scalar(select(func.max(DemoScriptVersion.version)).where(DemoScriptVersion.project_id == pid)) or 0) + 1
    db.add(DemoScriptVersion(project_id=pid, version=n, content=content, unverified_steps=flags, origin="edit", saved_by=cu.id))
    p.current_version = n
    audit(db, cu.user, "demo.script_saved", "demo_project", pid, version=n)
    db.commit()
    return {"version": n, "unverified_steps": flags}


@router.get("/projects/{pid}/export")
def export(pid: int, fmt: str = "docx", version: int | None = None, cu: CurrentUser = Depends(require("demo.export")),
           db: Session = Depends(get_db)):
    p = db.get(DemoProject, pid) or _404()
    v = db.scalar(select(DemoScriptVersion).where(DemoScriptVersion.project_id == pid,
                                                  DemoScriptVersion.version == (version or p.current_version))) or _404()
    data = script_docx(p.title, v.content, v.unverified_steps)
    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if fmt == "pdf":
        data, mime = docx_to_pdf(data), "application/pdf"
    audit(db, cu.user, "demo.exported", "demo_project", pid, version=v.version, format=fmt)
    db.commit()
    safe = "".join(ch for ch in p.title if ch.isalnum() or ch in " -_").strip() or "Demo"
    return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="Demo script - {safe} - v{v.version}.{fmt}"'})


@router.post("/projects/{pid}/outcome")
def set_outcome(pid: int, body: dict, cu: CurrentUser = Depends(require("demo.edit")), db: Session = Depends(get_db)):
    p = db.get(DemoProject, pid) or _404()
    p.outcome = body.get("outcome", "")
    audit(db, cu.user, "demo.outcome", "demo_project", pid, outcome=p.outcome)
    db.commit()
    return {"ok": True}


@router.post("/projects/{pid}/save-template")
def save_template(pid: int, body: dict, cu: CurrentUser = Depends(require("demo.manage_templates")), db: Session = Depends(get_db)):
    p = db.get(DemoProject, pid) or _404()
    v = db.scalar(select(DemoScriptVersion).where(DemoScriptVersion.project_id == pid, DemoScriptVersion.version == p.current_version)) or _404()
    t = DemoTemplate(name=body.get("name") or p.title, industry=(p.inputs or {}).get("industry", ""), content=v.content,
                     source_project_id=p.id, created_by=cu.id)
    db.add(t)
    db.flush()
    audit(db, cu.user, "demo.template_saved", "demo_template", t.id, project=pid)
    db.commit()
    return {"id": t.id}


@router.get("/templates")
def templates(cu: CurrentUser = Depends(require("demo.view")), db: Session = Depends(get_db)):
    return [{"id": t.id, "name": t.name, "industry": t.industry, "source_project_id": t.source_project_id, "content": t.content}
            for t in db.scalars(select(DemoTemplate).order_by(DemoTemplate.name))]


@router.post("/projects/{pid}/from-template/{tid}")
def from_template(pid: int, tid: int, cu: CurrentUser = Depends(require("demo.edit")), db: Session = Depends(get_db)):
    p = db.get(DemoProject, pid) or _404()
    t = db.get(DemoTemplate, tid) or _404()
    n = (db.scalar(select(func.max(DemoScriptVersion.version)).where(DemoScriptVersion.project_id == pid)) or 0) + 1
    library = {str(u.id): u for u in db.scalars(select(DemoUseCase))}
    db.add(DemoScriptVersion(project_id=pid, version=n, content=t.content, unverified_steps=verify_steps(t.content, library, ""),
                             origin="edit", saved_by=cu.id))
    p.current_version = n
    db.commit()
    return {"version": n}


def _404():
    raise HTTPException(404, "Not found")
