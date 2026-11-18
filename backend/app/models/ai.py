from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin, utcnow


class AIModel(Base, TimestampMixin):
    __tablename__ = "ai_models"
    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[str] = mapped_column(String(120), unique=True)
    label: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ModelPrice(Base, TimestampMixin):
    """Price per million tokens, maintained by the administrator (§5.5)."""
    __tablename__ = "model_prices"
    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[str] = mapped_column(String(120), unique=True)
    input_per_mtok: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    output_per_mtok: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")


class AgentConfiguration(Base, TimestampMixin):
    __tablename__ = "ai_agent_configurations"
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_key: Mapped[str] = mapped_column(String(60), unique=True)
    label: Mapped[str] = mapped_column(String(120))
    module: Mapped[str] = mapped_column(String(40))
    model_id: Mapped[str] = mapped_column(String(120))
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=16000)
    effort: Mapped[str] = mapped_column(String(10), default="medium")  # low | medium | high | xhigh | max
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=180)
    max_retries: Mapped[int] = mapped_column(Integer, default=2)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class EmbeddingConfiguration(Base, TimestampMixin):
    __tablename__ = "embedding_configurations"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(20))  # local | external
    model_name: Mapped[str] = mapped_column(String(120))
    dimension: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    reindex_job_id: Mapped[int | None] = mapped_column(BigInteger)
    # While a re-index runs, search keeps using the previous active configuration.
    pending_activation: Mapped[bool] = mapped_column(Boolean, default=False)


class AIUsageLog(Base):
    """No prompt or response text is ever stored here (§5.5)."""
    __tablename__ = "ai_usage_logs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    module: Mapped[str] = mapped_column(String(40), index=True)
    agent_key: Mapped[str] = mapped_column(String(60), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="chat")  # chat | embedding
    ref_type: Mapped[str] = mapped_column(String(40), default="")
    ref_id: Mapped[int | None] = mapped_column(Integer)
    job_id: Mapped[int | None] = mapped_column(BigInteger)
    model_id: Mapped[str] = mapped_column(String(120))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="ok")
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=0)


class Budget(Base, TimestampMixin):
    __tablename__ = "budgets"
    id: Mapped[int] = mapped_column(primary_key=True)
    month: Mapped[str] = mapped_column(String(7), unique=True)  # YYYY-MM
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    thresholds: Mapped[list] = mapped_column(JSONB, default=lambda: [80, 100])
    hard_stop: Mapped[bool] = mapped_column(Boolean, default=False)
    notified: Mapped[list] = mapped_column(JSONB, default=list)
