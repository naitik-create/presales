"""Shared customer context (§13), used by RFP Intelligence and Demo Intelligence. Deliberately small: no pipeline, values, owners, tasks or activities."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.deps import CurrentUser, require
from app.db import get_db
from app.models.core import CustomerContext
from app.common.sizes import parse_sizes

router = APIRouter(prefix="/customers", tags=["customers"])

FIELDS = ("name", "industry", "buyer_type", "region", "business_overview", "existing_tools", "infrastructure",
          "parsed_sizes", "competitors", "pain_points", "notes")


class CustomerIn(BaseModel):
    name: str
    industry: str = ""
    buyer_type: str = "Private"
    region: str = "India"
    business_overview: str = ""
    existing_tools: str = ""
    infrastructure: str = ""
    parsed_sizes: dict | None = None
    competitors: list[str] = []
    pain_points: str = ""
    notes: str = ""


def out(c: CustomerContext) -> dict:
    return {"id": c.id, **{f: getattr(c, f) for f in FIELDS}, "updated_at": c.updated_at}


@router.get("")
def list_customers(q: str | None = None, cu: CurrentUser = Depends(require("customers.view", "rfp.view", "demo.view")),
                   db: Session = Depends(get_db)):
    query = select(CustomerContext)
    if q:
        query = query.where(CustomerContext.name.ilike(f"%{q}%"))
    return [out(c) for c in db.scalars(query.order_by(CustomerContext.name).limit(500))]


@router.get("/{cid}")
def get_customer(cid: int, cu: CurrentUser = Depends(require("customers.view", "rfp.view", "demo.view")),
                 db: Session = Depends(get_db)):
    c = db.get(CustomerContext, cid)
    if not c:
        raise HTTPException(404, "Not found")
    return out(c)


@router.post("")
def create_customer(body: CustomerIn, cu: CurrentUser = Depends(require("customers.create")), db: Session = Depends(get_db)):
    data = body.model_dump()
    if data["parsed_sizes"] is None:
        data["parsed_sizes"] = parse_sizes(body.infrastructure)
    c = CustomerContext(**data, created_by=cu.id)
    db.add(c)
    db.flush()
    audit(db, cu.user, "customer.created", "customer", c.id, name=c.name)
    db.commit()
    return out(c)


@router.put("/{cid}")
def update_customer(cid: int, body: CustomerIn, cu: CurrentUser = Depends(require("customers.edit")), db: Session = Depends(get_db)):
    c = db.get(CustomerContext, cid)
    if not c:
        raise HTTPException(404, "Not found")
    data = body.model_dump()
    if data["parsed_sizes"] is None:
        data["parsed_sizes"] = parse_sizes(body.infrastructure) if body.infrastructure != c.infrastructure else c.parsed_sizes
    for k, v in data.items():
        setattr(c, k, v)
    audit(db, cu.user, "customer.updated", "customer", c.id, name=c.name)
    db.commit()
    return out(c)
