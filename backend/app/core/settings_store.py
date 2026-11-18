"""Administrator-editable settings held in system_settings, with defaults."""
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.core import SystemSetting


def defaults() -> dict:
    s = get_settings()
    return {
        "rfp_limits": {
            "max_concurrent_jobs": s.MAX_CONCURRENT_RFP_JOBS,
            "max_queued_jobs": s.MAX_QUEUED_RFP_JOBS,
            "job_timeout_seconds": 3600,
            "max_retries": 1,
            "max_document_mb": s.MAX_UPLOAD_MB,
            "max_documents_per_rfp": 30,
        },
        "password_policy": {"min_length": 10, "require_upper": True, "require_lower": True, "require_digit": True, "require_symbol": False},
        "session": {"hours": s.SESSION_HOURS, "max_login_attempts": s.MAX_LOGIN_ATTEMPTS, "lockout_minutes": s.LOCKOUT_MINUTES},
        "url_fetch_allowed_domains": [d.strip() for d in s.URL_FETCH_ALLOWED_DOMAINS.split(",") if d.strip()],
        "retrieval": {"top_k": 8, "chunk_chars": 1800, "chunk_overlap": 200},
    }


def get_setting(db: Session, key: str):
    row = db.get(SystemSetting, key)
    d = defaults().get(key)
    if row is None:
        return d
    if isinstance(d, dict) and isinstance(row.value, dict):
        return {**d, **row.value}
    return row.value


def set_setting(db: Session, key: str, value) -> None:
    row = db.get(SystemSetting, key)
    if row is None:
        db.add(SystemSetting(key=key, value=value))
    else:
        row.value = value
