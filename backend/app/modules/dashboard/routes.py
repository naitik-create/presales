"""Dashboard tiles (§18.3). Each tile follows permissions; this is not a task or CRM view."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.client import month_key, month_spend
from app.core.deps import CurrentUser, get_current_user
from app.db import get_db
from app.models.ai import AIUsageLog, Budget
from app.models.core import Job
from app.models.demo import DemoProject, DemoUseCase
from app.models.knowledge import KnowledgeSection, KnowledgeSource
from app.models.rfp import RFPComplianceResponse, RFPRequirement, RFPWorkspace
from app.models.scorecard import ScoringTransaction

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(cu: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    tiles: dict = {}
    if cu.has("rfp.view"):
        ws = db.scalars(select(RFPWorkspace).order_by(RFPWorkspace.updated_at.desc()).limit(6)).all()
        tiles["rfp_workspaces"] = [{"id": w.id, "title": w.name, "status": w.status, "due_date": w.due_date,
                                    "updated_at": w.updated_at} for w in ws]
        tiles["rfp_jobs"] = [{"id": j.id, "kind": j.kind, "status": j.status, "progress": j.progress, "ref_id": j.ref_id}
                             for j in db.scalars(select(Job).where(Job.queue == "rfp", Job.status.in_(["Queued", "Processing"]))
                                                 .order_by(Job.id))]
    if cu.has("demo.view"):
        tiles["demo_scripts"] = [{"id": d.id, "title": d.title, "version": d.current_version, "updated_at": d.updated_at}
                                 for d in db.scalars(select(DemoProject).order_by(DemoProject.updated_at.desc()).limit(6))]
    pending = {}
    if cu.has("rfp.approve"):
        pending["rfp_answers"] = db.scalar(select(func.count()).select_from(RFPComplianceResponse)
                                           .join(RFPRequirement, RFPRequirement.id == RFPComplianceResponse.requirement_id)
                                           .join(RFPWorkspace, RFPWorkspace.id == RFPRequirement.workspace_id)
                                           .where(RFPComplianceResponse.approved.is_(False), RFPRequirement.active.is_(True),
                                                  RFPWorkspace.status == "Awaiting Review"))
    if cu.has("knowledge.approve"):
        pending["knowledge_sources"] = db.scalar(select(func.count()).select_from(KnowledgeSource)
                                                 .where(KnowledgeSource.status == "Pending", KnowledgeSource.ingest_status == "Ready"))
    if cu.has("usecases.approve"):
        pending["use_cases"] = db.scalar(select(func.count()).select_from(DemoUseCase).where(DemoUseCase.status == "Draft"))
    if cu.has("scoring.approve"):
        pending["scoring"] = db.scalar(select(func.count()).select_from(ScoringTransaction)
                                       .where(ScoringTransaction.status == "Pending Approval"))
    if pending:
        tiles["pending"] = pending
    keys = cu.section_keys()
    if cu.has_area("knowledge") and keys:
        rows = db.execute(select(KnowledgeSource.ingest_status, func.count()).join(KnowledgeSection)
                          .where(KnowledgeSection.key.in_(keys)).group_by(KnowledgeSource.ingest_status)).all()
        tiles["ingestion"] = dict(rows)
    if cu.has("admin.usage"):
        b = db.scalar(select(Budget).where(Budget.month == month_key()))
        calls = db.scalar(select(func.count()).select_from(AIUsageLog).where(func.to_char(AIUsageLog.at, "YYYY-MM") == month_key()))
        tiles["usage"] = {"month": month_key(), "spent": float(month_spend(db)), "budget": float(b.amount) if b else None,
                          "calls": calls}
    return tiles
