"""Team Scorecard ledger (§11). No AI is involved and nothing here is ever sent to Claude or indexed for search."""
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.notify import notify
from app.models.core import User
from app.models.scorecard import (ScoreSnapshot, ScoringCategory, ScoringPeriod, ScoringRule, ScoringTransaction,
                                  WarningRecord)

THRESHOLDS = [
    (50, "First warning"),
    (30, "Second warning and improvement plan"),
    (10, "Third warning"),
    (0, "Manager review"),
]


def quarter_of(d: date) -> tuple[str, date, date]:
    q = (d.month - 1) // 3 + 1
    start = date(d.year, 3 * q - 2, 1)
    end = date(d.year + (q == 4), (3 * q) % 12 + 1, 1)
    from datetime import timedelta
    return f"{d.year}-Q{q}", start, end - timedelta(days=1)


def current_period(db: Session, today: date | None = None) -> ScoringPeriod:
    """Return the current quarter, creating it (and snapshotting the previous one) at rollover."""
    label, start, end = quarter_of(today or date.today())
    p = db.scalar(select(ScoringPeriod).where(ScoringPeriod.label == label))
    if p:
        return p
    prev = db.scalar(select(ScoringPeriod).order_by(ScoringPeriod.starts_on.desc()))
    p = ScoringPeriod(label=label, starts_on=start, ends_on=end, starting_points=100)
    db.add(p)
    db.flush()
    if prev:
        snapshot_period(db, prev)
    return p


def participants(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(User.is_scoring_participant.is_(True), User.is_active.is_(True)).order_by(User.full_name)))


def score(db: Session, period: ScoringPeriod, employee_id: int) -> int:
    pts = db.scalar(select(func.coalesce(func.sum(ScoringTransaction.points), 0)).where(
        ScoringTransaction.period_id == period.id, ScoringTransaction.employee_id == employee_id,
        ScoringTransaction.status == "Approved"))
    return period.starting_points + int(pts or 0)


def by_category(db: Session, period: ScoringPeriod, employee_id: int | None = None) -> dict:
    q = (select(ScoringCategory.name, func.sum(func.greatest(ScoringTransaction.points, 0)),
                func.sum(func.least(ScoringTransaction.points, 0)))
         .join(ScoringRule, ScoringRule.id == ScoringTransaction.rule_id)
         .join(ScoringCategory, ScoringCategory.id == ScoringRule.category_id)
         .where(ScoringTransaction.period_id == period.id, ScoringTransaction.status == "Approved")
         .group_by(ScoringCategory.name))
    if employee_id:
        q = q.where(ScoringTransaction.employee_id == employee_id)
    return {name: {"rewards": int(r or 0), "deductions": int(d or 0)} for name, r, d in db.execute(q)}


def snapshot_period(db: Session, period: ScoringPeriod) -> None:
    for u in participants(db):
        if not db.scalar(select(ScoreSnapshot).where(ScoreSnapshot.period_id == period.id, ScoreSnapshot.employee_id == u.id)):
            db.add(ScoreSnapshot(period_id=period.id, employee_id=u.id, score=score(db, period, u.id),
                                 by_category=by_category(db, period, u.id)))


def apply_warnings(db: Session, period: ScoringPeriod, employee_id: int, tx: ScoringTransaction) -> list[WarningRecord]:
    """Issue each warning once per threshold crossing in a period (§11.6). Records only; no employment action."""
    s = score(db, period, employee_id)
    issued = []
    for threshold, level in THRESHOLDS:
        crossed = s <= 0 if threshold == 0 else s < threshold
        if not crossed:
            continue
        exists = db.scalar(select(WarningRecord).where(WarningRecord.period_id == period.id,
                                                       WarningRecord.employee_id == employee_id, WarningRecord.threshold == threshold))
        if exists:
            continue
        w = WarningRecord(period_id=period.id, employee_id=employee_id, threshold=threshold, level=level, score_at=s,
                          reason=f"Score {s} after transaction #{tx.id}: {tx.reason[:200]}", transaction_id=tx.id)
        db.add(w)
        issued.append(w)
        notify(db, employee_id, "scoring_warning", level, f"Your score is {s}. Open the Team Scorecard to acknowledge.", "/scorecard")
    return issued
