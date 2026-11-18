"""Global search (§14.4). Respects permissions; scoring records are never included."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, get_current_user
from app.db import get_db
from app.models.demo import DemoProject
from app.models.knowledge import KnowledgeSection, KnowledgeSource
from app.models.rfp import RFPWorkspace

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def search(q: str, cu: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    term = f"%{q.strip()}%"
    if len(q.strip()) < 2:
        return []
    out = []
    if cu.has("rfp.view"):
        out += [{"type": "RFP workspace", "title": w.name, "href": f"/rfp/{w.id}", "status": w.status}
                for w in db.scalars(select(RFPWorkspace).where(RFPWorkspace.name.ilike(term)).limit(10))]
    if cu.has("demo.view"):
        out += [{"type": "Demo script", "title": d.title, "href": f"/demo/{d.id}", "status": d.outcome}
                for d in db.scalars(select(DemoProject).where(DemoProject.title.ilike(term)).limit(10))]
    keys = cu.section_keys()
    if keys:
        rows = db.execute(select(KnowledgeSource, KnowledgeSection.name)
                          .join(KnowledgeSection, KnowledgeSection.id == KnowledgeSource.section_id)
                          .where(KnowledgeSection.key.in_(keys), KnowledgeSource.title.ilike(term),
                                 KnowledgeSource.status.in_(["Approved", "Pending"]))
                          .limit(15)).all()
        out += [{"type": f"Knowledge: {sec}", "title": s.title, "href": f"/knowledge?source={s.id}", "status": s.status}
                for s, sec in rows]
    return out
