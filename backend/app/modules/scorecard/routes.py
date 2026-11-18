from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.deps import CurrentUser, get_current_user, require
from app.core.notify import notify, notify_permission
from app.db import get_db, utcnow
from app.models.core import User
from app.models.scorecard import (ScoreSnapshot, ScoringCategory, ScoringComment, ScoringPeriod, ScoringRule,
                                  ScoringTransaction, WarningRecord)
from app.modules.auth.routes import can_see_scorecard
from app.modules.scorecard.service import apply_warnings, by_category, current_period, participants, score

router = APIRouter(prefix="/scorecard", tags=["scorecard"])
MANAGER_PERMS = ("scoring.view_all", "scoring.approve", "scoring.view_reports")


def _guard(cu: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not can_see_scorecard(cu):
        raise HTTPException(404, "Not found")  # non-participants see nothing at all (§11.8)
    return cu


def _can_see_employee(cu: CurrentUser, employee_id: int) -> bool:
    return cu.has_any(*MANAGER_PERMS) or (employee_id == cu.id and cu.has("scoring.view_own") and cu.user.is_scoring_participant)


def tx_out(t: ScoringTransaction, rules: dict, users: dict, comments: list | None = None) -> dict:
    r = rules.get(t.rule_id)
    return {"id": t.id, "employee_id": t.employee_id, "employee": users.get(t.employee_id, ""), "rule_id": t.rule_id,
            "rule": r.name if r else "", "category_id": r.category_id if r else None, "points": t.points, "reason": t.reason,
            "evidence": t.evidence, "status": t.status, "proposed_by": users.get(t.proposed_by, ""), "proposed_at": t.proposed_at,
            "decided_by": users.get(t.decided_by, ""), "decided_at": t.decided_at, "decision_note": t.decision_note,
            "exception_note": t.exception_note, "reverses_id": t.reverses_id,
            "comments": [{"id": c.id, "kind": c.kind, "text": c.text, "author": users.get(c.author_id, ""), "at": c.at}
                         for c in (comments or [])]}


def _maps(db: Session) -> tuple[dict, dict]:
    return {r.id: r for r in db.scalars(select(ScoringRule))}, {u.id: u.full_name for u in db.scalars(select(User))}


# ---------- overview ----------
@router.get("/overview")
def overview(cu: CurrentUser = Depends(_guard), db: Session = Depends(get_db)):
    period = current_period(db)
    db.commit()
    me = None
    if cu.user.is_scoring_participant and cu.has("scoring.view_own"):
        me = {"score": score(db, period, cu.id), "by_category": by_category(db, period, cu.id)}
    team = None
    if cu.has_any("scoring.view_all", "scoring.view_reports"):
        team = [{"employee_id": u.id, "name": u.full_name, "score": score(db, period, u.id)} for u in participants(db)]
    pending = None
    if cu.has("scoring.approve"):
        rules, users = _maps(db)
        pending = [tx_out(t, rules, users) for t in db.scalars(select(ScoringTransaction)
                                                                .where(ScoringTransaction.status == "Pending Approval")
                                                                .order_by(ScoringTransaction.proposed_at))]
    return {"period": {"id": period.id, "label": period.label, "starts_on": period.starts_on, "ends_on": period.ends_on},
            "me": me, "team": team, "pending": pending,
            "can": {"propose": cu.has_any("scoring.propose", "scoring.approve"), "approve": cu.has("scoring.approve"),
                    "manage_rules": cu.has("scoring.manage_rules"), "reports": cu.has("scoring.view_reports")}}


# ---------- rules ----------
class RuleIn(BaseModel):
    category_id: int
    name: str
    points: int
    description: str = ""


@router.get("/categories")
def categories(cu: CurrentUser = Depends(_guard), db: Session = Depends(get_db)):
    return [{"id": c.id, "name": c.name} for c in db.scalars(select(ScoringCategory).order_by(ScoringCategory.sort))]


@router.post("/categories")
def add_category(body: dict, cu: CurrentUser = Depends(require("scoring.manage_rules")), db: Session = Depends(get_db)):
    c = ScoringCategory(name=body["name"], sort=body.get("sort", 100))
    db.add(c)
    db.flush()
    audit(db, cu.user, "scoring.category_created", "scoring_category", c.id, name=c.name)
    db.commit()
    return {"id": c.id}


@router.get("/rules")
def rules(include_inactive: bool = False, cu: CurrentUser = Depends(_guard), db: Session = Depends(get_db)):
    q = select(ScoringRule)
    if not include_inactive:
        q = q.where(ScoringRule.active.is_(True))
    return [{"id": r.id, "category_id": r.category_id, "name": r.name, "points": r.points, "description": r.description,
             "active": r.active, "replaces_id": r.replaces_id} for r in db.scalars(q.order_by(ScoringRule.category_id, ScoringRule.name))]


@router.post("/rules")
def create_rule(body: RuleIn, cu: CurrentUser = Depends(require("scoring.manage_rules")), db: Session = Depends(get_db)):
    if body.points == 0:
        raise HTTPException(400, "A rule must have a non-zero point value")
    r = ScoringRule(**body.model_dump())
    db.add(r)
    db.flush()
    audit(db, cu.user, "scoring.rule_created", "scoring_rule", r.id, **body.model_dump())
    db.commit()
    return {"id": r.id}


@router.put("/rules/{rid}")
def edit_rule(rid: int, body: RuleIn, cu: CurrentUser = Depends(require("scoring.manage_rules")), db: Session = Depends(get_db)):
    """Editing a rule creates a new version; the change applies only to later transactions."""
    old = db.get(ScoringRule, rid)
    if not old or not old.active:
        raise HTTPException(404, "Rule not found")
    old.active = False
    new = ScoringRule(**body.model_dump(), replaces_id=old.id)
    db.add(new)
    db.flush()
    audit(db, cu.user, "scoring.rule_changed", "scoring_rule", new.id, replaces=old.id,
          before={"name": old.name, "points": old.points}, after=body.model_dump())
    db.commit()
    return {"id": new.id}


@router.delete("/rules/{rid}")
def retire_rule(rid: int, cu: CurrentUser = Depends(require("scoring.manage_rules")), db: Session = Depends(get_db)):
    r = db.get(ScoringRule, rid)
    if not r:
        raise HTTPException(404, "Rule not found")
    r.active = False
    audit(db, cu.user, "scoring.rule_retired", "scoring_rule", rid)
    db.commit()
    return {"ok": True}


# ---------- transactions ----------
class ProposeIn(BaseModel):
    employee_id: int
    rule_id: int
    reason: str
    evidence: str


@router.get("/participants")
def list_participants(cu: CurrentUser = Depends(require("scoring.propose", "scoring.approve", "scoring.view_all")),
                      db: Session = Depends(get_db)):
    return [{"id": u.id, "name": u.full_name} for u in participants(db)]


@router.post("/transactions")
def propose(body: ProposeIn, cu: CurrentUser = Depends(require("scoring.propose", "scoring.approve")), db: Session = Depends(get_db)):
    emp = db.get(User, body.employee_id)
    if not emp or not emp.is_scoring_participant:
        raise HTTPException(400, "The employee is not a scoring participant")
    rule = db.get(ScoringRule, body.rule_id)
    if not rule or not rule.active:
        raise HTTPException(400, "Choose an active rule")
    if not body.reason.strip() or not body.evidence.strip():
        raise HTTPException(400, "A reason and evidence are required")
    period = current_period(db)
    t = ScoringTransaction(period_id=period.id, employee_id=emp.id, rule_id=rule.id, points=rule.points, reason=body.reason,
                           evidence=body.evidence, proposed_by=cu.id)
    db.add(t)
    db.flush()
    audit(db, cu.user, "scoring.proposed", "scoring_transaction", t.id, employee=emp.id, rule=rule.name, points=rule.points)
    notify_permission(db, "scoring.approve", "scoring_pending", "Scoring transaction awaiting approval",
                      f"{rule.name} for {emp.full_name}", "/scorecard")
    db.commit()
    return {"id": t.id}


class DecisionIn(BaseModel):
    note: str = ""
    exception: bool = False


@router.post("/transactions/{tid}/approve")
def approve(tid: int, body: DecisionIn, cu: CurrentUser = Depends(require("scoring.approve")), db: Session = Depends(get_db)):
    t = db.get(ScoringTransaction, tid)
    if not t or t.status != "Pending Approval":
        raise HTTPException(400, "Only pending transactions can be approved")
    t.status, t.decided_by, t.decided_at, t.decision_note = "Approved", cu.id, utcnow(), body.note
    db.flush()
    period = db.get(ScoringPeriod, t.period_id)
    warnings = apply_warnings(db, period, t.employee_id, t)
    audit(db, cu.user, "scoring.approved", "scoring_transaction", t.id, points=t.points, warnings=[w.level for w in warnings])
    notify(db, t.employee_id, "scoring_update", "Your score was updated",
           f"{'+' if t.points > 0 else ''}{t.points} points: {t.reason[:150]}", "/scorecard")
    db.commit()
    return {"ok": True, "score": score(db, period, t.employee_id), "warnings": [w.level for w in warnings]}


@router.post("/transactions/{tid}/reject")
def reject(tid: int, body: DecisionIn, cu: CurrentUser = Depends(require("scoring.approve")), db: Session = Depends(get_db)):
    t = db.get(ScoringTransaction, tid)
    if not t or t.status != "Pending Approval":
        raise HTTPException(400, "Only pending transactions can be rejected")
    if body.exception and not body.note.strip():
        raise HTTPException(400, "Describe the exception")
    t.status, t.decided_by, t.decided_at, t.decision_note = "Rejected", cu.id, utcnow(), body.note
    if body.exception:
        t.exception_note = body.note
    audit(db, cu.user, "scoring.rejected", "scoring_transaction", t.id, exception=body.exception, note=body.note)
    db.commit()
    return {"ok": True}


@router.post("/transactions/{tid}/reverse")
def reverse(tid: int, body: DecisionIn, cu: CurrentUser = Depends(require("scoring.approve")), db: Session = Depends(get_db)):
    """Corrections are new reversing transactions that reference the original (§11.5)."""
    t = db.get(ScoringTransaction, tid)
    if not t or t.status != "Approved":
        raise HTTPException(400, "Only approved transactions can be reversed")
    if db.scalar(select(ScoringTransaction).where(ScoringTransaction.reverses_id == t.id, ScoringTransaction.status != "Rejected")):
        raise HTTPException(400, "This transaction already has a reversal")
    if not body.note.strip():
        raise HTTPException(400, "A reason for the correction is required")
    period = current_period(db)
    r = ScoringTransaction(period_id=period.id, employee_id=t.employee_id, rule_id=t.rule_id, points=-t.points,
                           reason=f"Reversal of #{t.id}: {body.note}", evidence=f"Correction of transaction #{t.id}",
                           reverses_id=t.id, proposed_by=cu.id)
    db.add(r)
    db.flush()
    audit(db, cu.user, "scoring.reversal_proposed", "scoring_transaction", r.id, reverses=t.id)
    db.commit()
    return {"id": r.id}


@router.get("/transactions")
def transactions(employee_id: int | None = None, period_id: int | None = None, status: str | None = None,
                 cu: CurrentUser = Depends(_guard), db: Session = Depends(get_db)):
    q = select(ScoringTransaction)
    if not cu.has_any(*MANAGER_PERMS):
        q = q.where(ScoringTransaction.employee_id == cu.id)  # employees see only their own
    elif employee_id:
        q = q.where(ScoringTransaction.employee_id == employee_id)
    if period_id:
        q = q.where(ScoringTransaction.period_id == period_id)
    if status:
        q = q.where(ScoringTransaction.status == status)
    rows = db.scalars(q.order_by(ScoringTransaction.id.desc()).limit(1000)).all()
    comments: dict[int, list] = {}
    if rows:
        for c in db.scalars(select(ScoringComment).where(ScoringComment.transaction_id.in_([t.id for t in rows])).order_by(ScoringComment.id)):
            comments.setdefault(c.transaction_id, []).append(c)
    rules, users = _maps(db)
    return [tx_out(t, rules, users, comments.get(t.id)) for t in rows]


class CommentIn(BaseModel):
    kind: str = "comment"  # comment | review_request | review_outcome
    text: str


@router.post("/transactions/{tid}/comments")
def comment(tid: int, body: CommentIn, cu: CurrentUser = Depends(_guard), db: Session = Depends(get_db)):
    t = db.get(ScoringTransaction, tid)
    if not t or not _can_see_employee(cu, t.employee_id):
        raise HTTPException(404, "Not found")
    if body.kind in ("comment", "review_request") and t.employee_id != cu.id and not cu.has("scoring.approve"):
        raise HTTPException(403, "Only the employee concerned can comment or request a review")
    if body.kind == "review_outcome" and not cu.has("scoring.approve"):
        raise HTTPException(403, "Only the Presales Manager records review outcomes")
    if body.kind not in ("comment", "review_request", "review_outcome") or not body.text.strip():
        raise HTTPException(400, "Invalid comment")
    c = ScoringComment(transaction_id=tid, author_id=cu.id, kind=body.kind, text=body.text)
    db.add(c)
    db.flush()
    audit(db, cu.user, f"scoring.{body.kind}", "scoring_transaction", tid)
    if body.kind == "review_request":
        notify_permission(db, "scoring.approve", "scoring_review", "Review requested on a scoring transaction",
                          body.text[:200], "/scorecard")
    elif body.kind == "review_outcome":
        notify(db, t.employee_id, "scoring_review", "Review outcome recorded", body.text[:200], "/scorecard")
    db.commit()
    return {"id": c.id}


# ---------- warnings ----------
@router.get("/warnings")
def warnings(employee_id: int | None = None, cu: CurrentUser = Depends(_guard), db: Session = Depends(get_db)):
    q = select(WarningRecord)
    if not cu.has_any(*MANAGER_PERMS):
        q = q.where(WarningRecord.employee_id == cu.id)
    elif employee_id:
        q = q.where(WarningRecord.employee_id == employee_id)
    users = {u.id: u.full_name for u in db.scalars(select(User))}
    periods = {p.id: p.label for p in db.scalars(select(ScoringPeriod))}
    return [{"id": w.id, "employee": users.get(w.employee_id, ""), "employee_id": w.employee_id, "period": periods.get(w.period_id),
             "level": w.level, "threshold": w.threshold, "score_at": w.score_at, "reason": w.reason, "at": w.at,
             "acknowledged_at": w.acknowledged_at} for w in db.scalars(q.order_by(WarningRecord.at.desc()))]


@router.post("/warnings/{wid}/acknowledge")
def acknowledge(wid: int, cu: CurrentUser = Depends(_guard), db: Session = Depends(get_db)):
    w = db.get(WarningRecord, wid)
    if not w or w.employee_id != cu.id:
        raise HTTPException(404, "Not found")
    if w.acknowledged_at:
        raise HTTPException(400, "Already acknowledged")
    w.acknowledged_at = utcnow()
    audit(db, cu.user, "scoring.warning_acknowledged", "warning", wid)
    db.commit()
    return {"ok": True}


# ---------- reports ----------
@router.get("/reports")
def reports(cu: CurrentUser = Depends(require("scoring.view_reports", "scoring.view_all")), db: Session = Depends(get_db)):
    current = current_period(db)
    db.commit()
    periods = db.scalars(select(ScoringPeriod).order_by(ScoringPeriod.starts_on)).all()
    snaps = {(s.period_id, s.employee_id): s.score for s in db.scalars(select(ScoreSnapshot))}
    people = participants(db)
    qoq = [{"employee_id": u.id, "name": u.full_name,
            "scores": {p.label: (score(db, p, u.id) if p.id == current.id else snaps.get((p.id, u.id))) for p in periods}}
           for u in people]
    team_cat = by_category(db, current)
    pending = db.scalars(select(ScoringTransaction).where(ScoringTransaction.status == "Pending Approval")).all()
    return {"period": current.label, "periods": [p.label for p in periods], "quarter_on_quarter": qoq,
            "by_category": team_cat, "pending_count": len(pending),
            "individual": [{"employee_id": u.id, "name": u.full_name, "score": score(db, current, u.id),
                            "by_category": by_category(db, current, u.id)} for u in people]}
