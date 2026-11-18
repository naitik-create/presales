from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin, utcnow


class KnowledgeSection(Base, TimestampMixin):
    __tablename__ = "knowledge_sections"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    used_by: Mapped[str] = mapped_column(String(200), default="")
    # Source priority when answers conflict (§6.5): 1 = current docs, 2 = internal knowledge, 3 = submitted RFPs
    priority: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=100)


class KnowledgeSource(Base, TimestampMixin):
    __tablename__ = "knowledge_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("knowledge_sections.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # file | url
    title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(1000), default="")
    product: Mapped[str] = mapped_column(String(20), default="Both")  # ObserveOps | ServiceOps | Both
    product_version: Mapped[str] = mapped_column(String(40), default="")
    document_type: Mapped[str] = mapped_column(String(60), default="")
    publication_date: Mapped[date | None] = mapped_column(Date)
    label: Mapped[str] = mapped_column(String(40), default="")  # e.g. "verified" / "internal observation" for competitor info
    status: Mapped[str] = mapped_column(String(20), default="Pending")  # Pending | Approved | Rejected | Disabled
    ingest_status: Mapped[str] = mapped_column(String(20), default="Queued")  # Queued | Processing | Ready | Failed
    ingest_error: Mapped[str] = mapped_column(Text, default="")
    current_version: Mapped[int] = mapped_column(Integer, default=0)
    last_fetch_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_fetch_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duplicate_of: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("knowledge_sources.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    file_id: Mapped[int | None] = mapped_column(ForeignKey("stored_files.id"))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    used_ocr: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding_model: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("knowledge_sources.id", ondelete="CASCADE"), index=True)
    section_id: Mapped[int] = mapped_column(Integer, index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    section_path: Mapped[str] = mapped_column(String(500), default="")
    page: Mapped[str] = mapped_column(String(40), default="")
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    embedding = mapped_column(Vector(), nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(120), default="", index=True)
    embedding_dim: Mapped[int] = mapped_column(Integer, default=0)


class SourceApproval(Base):
    __tablename__ = "source_approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("knowledge_sources.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(20))
    by_user: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SizingRule(Base, TimestampMixin):
    """One row of the product team's sizing guide (§10.4). conditions: {"input": [min, max]} inclusive-exclusive."""
    __tablename__ = "sizing_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    product: Mapped[str] = mapped_column(String(20))
    component: Mapped[str] = mapped_column(String(120))
    conditions: Mapped[dict] = mapped_column(JSONB, default=dict)
    result: Mapped[dict] = mapped_column(JSONB, default=dict)  # {"cpu": "16 vCPU", "ram": "64 GB", "disk": "2 TB SSD", "nodes": 1}
    source: Mapped[str] = mapped_column(String(300), default="")
    sort: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ChatConversation(Base, TimestampMixin):
    __tablename__ = "chat_conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="New conversation")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("chat_conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(12))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSONB, default=list)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnswerFeedback(Base):
    __tablename__ = "answer_feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("chat_messages.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    helpful: Mapped[bool] = mapped_column(Boolean)
    comment: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QuestionGap(Base):
    __tablename__ = "question_gap_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(30))  # not_found | not_helpful
    message_id: Mapped[int | None] = mapped_column(ForeignKey("chat_messages.id", ondelete="SET NULL"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    comment: Mapped[str] = mapped_column(Text, default="")
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SubmittedRFP(Base, TimestampMixin):
    __tablename__ = "submitted_rfps"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer: Mapped[str] = mapped_column(String(200))
    industry: Mapped[str] = mapped_column(String(60), default="")
    submitted_on: Mapped[date | None] = mapped_column(Date)
    product_version: Mapped[str] = mapped_column(String(40), default="")
    title: Mapped[str] = mapped_column(String(300), default="")
    held_back_for_testing: Mapped[bool] = mapped_column(Boolean, default=False)
    workspace_id: Mapped[int | None] = mapped_column(Integer)
    file_ids: Mapped[list] = mapped_column(JSONB, default=list)  # [{"file_id":..,"role":"rfp|compliance|proposal|other"}]
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class SubmittedRequirementResponse(Base):
    __tablename__ = "submitted_requirement_responses"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    submitted_rfp_id: Mapped[int] = mapped_column(ForeignKey("submitted_rfps.id", ondelete="CASCADE"), index=True)
    requirement: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="")
    response: Mapped[str] = mapped_column(Text, default="")
    reference: Mapped[str] = mapped_column(String(300), default="")
    embedding = mapped_column(Vector(), nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(120), default="")
