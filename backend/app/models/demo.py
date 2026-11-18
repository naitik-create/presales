from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin, utcnow


class DemoUseCase(Base, TimestampMixin):
    __tablename__ = "demo_use_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    product: Mapped[str] = mapped_column(String(20))
    module_key: Mapped[str] = mapped_column(String(10))
    pain: Mapped[str] = mapped_column(Text, default="")
    industries: Mapped[list] = mapped_column(JSONB, default=list)
    navigation: Mapped[list] = mapped_column(JSONB, default=list)  # ordered screens / menu paths
    what_to_show: Mapped[str] = mapped_column(Text, default="")
    expected_result: Mapped[str] = mapped_column(Text, default="")
    talk_track: Mapped[str] = mapped_column(Text, default="")
    value_statement: Mapped[str] = mapped_column(Text, default="")
    differentiator: Mapped[str] = mapped_column(Text, default="")
    objections: Mapped[list] = mapped_column(JSONB, default=list)  # [{"objection":..,"answer":..}]
    prerequisites: Mapped[str] = mapped_column(Text, default="")
    minutes: Mapped[int] = mapped_column(Integer, default=10)
    status: Mapped[str] = mapped_column(String(20), default="Draft")  # Draft | Approved
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class DemoProject(Base, TimestampMixin):
    __tablename__ = "demo_projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer_contexts.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    inputs: Mapped[dict] = mapped_column(JSONB, default=dict)
    current_version: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[str] = mapped_column(String(20), default="")  # "" | Won | Lost
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class DemoScriptVersion(Base):
    """content follows §9.4: opening, end_result_first, agenda[], use_cases[], objections[], closing, checklist[]."""
    __tablename__ = "demo_scripts"
    __table_args__ = (UniqueConstraint("project_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("demo_projects.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(JSONB)
    unverified_steps: Mapped[list] = mapped_column(JSONB, default=list)
    origin: Mapped[str] = mapped_column(String(10), default="ai")  # ai | edit
    saved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DemoTemplate(Base, TimestampMixin):
    """A script that led to a win, saved for reuse (§9.5)."""
    __tablename__ = "demo_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    industry: Mapped[str] = mapped_column(String(60), default="")
    content: Mapped[dict] = mapped_column(JSONB)
    source_project_id: Mapped[int | None] = mapped_column(ForeignKey("demo_projects.id", ondelete="SET NULL"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
