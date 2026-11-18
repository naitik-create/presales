"""Team Scorecard. Never read by search or AI services (§11.8)."""
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin, utcnow


class ScoringCategory(Base):
    __tablename__ = "scoring_categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    sort: Mapped[int] = mapped_column(Integer, default=100)


class ScoringRule(Base, TimestampMixin):
    """Editing a rule creates a new row and deactivates the old one, so earlier transactions keep their values."""
    __tablename__ = "scoring_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("scoring_categories.id"))
    name: Mapped[str] = mapped_column(String(200))
    points: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    replaces_id: Mapped[int | None] = mapped_column(Integer)


class ScoringPeriod(Base):
    __tablename__ = "scoring_periods"
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(10), unique=True)  # 2026-Q4
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    starting_points: Mapped[int] = mapped_column(Integer, default=100)


class ScoringTransaction(Base):
    """Once status is Approved or Rejected the row is immutable (database trigger)."""
    __tablename__ = "scoring_transactions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("scoring_periods.id"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("scoring_rules.id"))
    points: Mapped[int] = mapped_column(Integer)  # copied from the rule at proposal time
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)
    evidence_file_id: Mapped[int | None] = mapped_column(ForeignKey("stored_files.id"))
    reverses_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default="Pending Approval")  # Pending Approval | Approved | Rejected
    proposed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    proposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str] = mapped_column(Text, default="")
    exception_note: Mapped[str] = mapped_column(Text, default="")


class ScoringComment(Base):
    """Employee comments and review requests. Immutable (database trigger)."""
    __tablename__ = "scoring_comments"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("scoring_transactions.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(20))  # comment | review_request | review_outcome
    text: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WarningRecord(Base):
    __tablename__ = "warning_records"
    __table_args__ = (UniqueConstraint("period_id", "employee_id", "threshold"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("scoring_periods.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    threshold: Mapped[int] = mapped_column(Integer)  # 50 | 30 | 10 | 0
    level: Mapped[str] = mapped_column(String(60))
    score_at: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text, default="")
    transaction_id: Mapped[int | None] = mapped_column(BigInteger)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ScoreSnapshot(Base):
    """Closing score per participant per period, written at quarter rollover."""
    __tablename__ = "score_snapshots"
    __table_args__ = (UniqueConstraint("period_id", "employee_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("scoring_periods.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    score: Mapped[int] = mapped_column(Integer)
    by_category: Mapped[dict] = mapped_column(JSONB, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
