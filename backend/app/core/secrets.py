"""API keys stored encrypted in the database (Administration > API keys).

Values are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) using SECRETS_ENCRYPTION_KEY from the environment,
so a database dump alone never reveals a key. Plain values are never returned to the browser or written to logs.
"""
import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.core import ApiCredential

log = logging.getLogger("secrets")

# Providers the application knows. 'used_for' is shown in the admin screen.
PROVIDERS = {
    "anthropic": {"label": "Anthropic Claude", "env": "ANTHROPIC_API_KEY", "used_for": "Agents set to a Claude model (the default)", "prefix": "sk-ant-"},
    "voyage": {"label": "Voyage AI embeddings", "env": "EXTERNAL_EMBEDDING_API_KEY", "used_for": "External embedding option", "prefix": "pa-"},
    "openai": {"label": "OpenAI", "env": "", "used_for": "Agents set to an OpenAI model", "prefix": ""},
    "google": {"label": "Google Gemini", "env": "", "used_for": "Agents set to a Gemini model", "prefix": ""},
    "azure_openai": {"label": "Azure OpenAI", "env": "", "used_for": "Agents set to an Azure OpenAI deployment", "prefix": ""},
}


def _fernet() -> Fernet:
    s = get_settings()
    if s.SECRETS_ENCRYPTION_KEY:
        return Fernet(s.SECRETS_ENCRYPTION_KEY.encode())
    # Fallback: derive from APP_SECRET_KEY. Changing APP_SECRET_KEY then makes stored keys unreadable.
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("secrets:" + s.APP_SECRET_KEY).encode()).digest()))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def mask(value: str) -> str:
    return f"…{value[-4:]}" if len(value) >= 8 else "…"


def set_secret(db: Session, provider: str, value: str, user_id: int | None, label: str = "") -> ApiCredential:
    row = db.scalar(select(ApiCredential).where(ApiCredential.provider == provider))
    if row is None:
        row = ApiCredential(provider=provider)
        db.add(row)
    row.ciphertext = encrypt(value)
    row.last4 = value[-4:]
    row.label = label or PROVIDERS.get(provider, {}).get("label", provider)
    row.updated_by = user_id
    row.last_test_ok = None
    row.last_test_message = ""
    return row


def get_secret(db: Session, provider: str) -> str:
    """Key saved in the database, else the environment fallback, else ''."""
    row = db.scalar(select(ApiCredential).where(ApiCredential.provider == provider))
    if row is not None:
        try:
            return decrypt(row.ciphertext)
        except InvalidToken:
            log.error("Stored %s key cannot be decrypted; check SECRETS_ENCRYPTION_KEY", provider)
            return ""
    env = PROVIDERS.get(provider, {}).get("env")
    return getattr(get_settings(), env, "") if env else ""


def source_of(db: Session, provider: str) -> str:
    if db.scalar(select(ApiCredential.id).where(ApiCredential.provider == provider)):
        return "database"
    env = PROVIDERS.get(provider, {}).get("env")
    return "environment" if env and getattr(get_settings(), env, "") else "none"
