from collections.abc import Iterator
from datetime import datetime, timezone

from sqlalchemy import DateTime, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


_engine = None
_SessionLocal: sessionmaker | None = None


def configure(url: str | None = None) -> None:
    global _engine, _SessionLocal
    _engine = create_engine(url or get_settings().DATABASE_URL, pool_pre_ping=True, pool_size=10)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def engine():
    if _engine is None:
        configure()
    return _engine


def SessionLocal() -> Session:
    if _SessionLocal is None:
        configure()
    return _SessionLocal()  # type: ignore[misc]


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
