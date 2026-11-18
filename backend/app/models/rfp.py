from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin, utcnow


class RFPWorkspace(Base, TimestampMixin):
    __tablename__ = "rfp_workspaces"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer_contexts.id"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    product_version: Mapped[str] = mapped_column(String(40), default="")
    products: Mapped[list] = mapped_column(JSONB, default=lambda: ["ObserveOps", "ServiceOps"])
    status: Mapped[str] = mapped_column(String(20), default="Uploaded")  # §8.9 job states plus Submitted
    due_date: Mapped[date | None] = mapped_column(Date)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("rfp_templates.id"))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class RFPDocument(Base):
    __tablename__ = "rfp_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("rfp_workspaces.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("stored_files.id"))
    name: Mapped[str] = mapped_column(String(300))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    role: Mapped[str] = mapped_column(String(20), default="rfp")  # rfp | corrigendum | submitted
    extracted: Mapped[list] = mapped_column(JSONB, default=list)  # [{"ref": "p.4", "section": "...", "text": "..."}]
    used_ocr: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="Uploaded")
    error: Mapped[str] = mapped_column(Text, default="")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RFPRequirement(Base, TimestampMixin):
    __tablename__ = "rfp_requirements"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("rfp_workspaces.id", ondelete="CASCADE"), index=True)
    number: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(60), default="Technical")
    source_file: Mapped[str] = mapped_column(String(300), default="")
    source_ref: Mapped[str] = mapped_column(String(100), default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    change: Mapped[str] = mapped_column(String(10), default="")  # "" | added | changed | removed (corrigendum)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    embedding = mapped_column(Vector(), nullable=True)


class RFPComplianceResponse(Base, TimestampMixin):
    __tablename__ = "rfp_compliance_responses"
    id: Mapped[int] = mapped_column(primary_key=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("rfp_requirements.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(40), default="Needs Product Validation")
    response: Mapped[str] = mapped_column(Text, default="")
    explanation: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[str] = mapped_column(Text, default="")
    sources: Mapped[list] = mapped_column(JSONB, default=list)  # trace to supporting sources
    validation_remarks: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(30), default="ai")  # ai | submitted_rfp | manual
    origin_detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RFPAgentRun(Base):
    """Outputs of document-level agents (analysis, risks, architecture, PQ/TQ, BOQ, synopsis, queries)."""
    __tablename__ = "rfp_agent_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("rfp_workspaces.id", ondelete="CASCADE"), index=True)
    agent_key: Mapped[str] = mapped_column(String(60))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    output: Mapped[dict] = mapped_column(JSONB, default=dict)
    edited_output: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="ok")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    job_id: Mapped[int | None] = mapped_column(BigInteger)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RFPProposal(Base, TimestampMixin):
    __tablename__ = "rfp_proposals"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("rfp_workspaces.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("rfp_templates.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[dict] = mapped_column(JSONB, default=dict)  # {placeholder: text}
    file_id: Mapped[int | None] = mapped_column(ForeignKey("stored_files.id"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class RFPTemplate(Base, TimestampMixin):
    __tablename__ = "rfp_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), default="template")  # template | sample
    module: Mapped[str] = mapped_column(String(10), default="rfp")  # rfp | demo
    file_id: Mapped[int] = mapped_column(ForeignKey("stored_files.id"))
    placeholders: Mapped[list] = mapped_column(JSONB, default=list)  # [{"name": "executive_summary", "description": ".."}]
    version: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
