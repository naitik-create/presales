import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher()

DEFAULT_POLICY = {"min_length": 10, "require_upper": True, "require_lower": True, "require_digit": True, "require_symbol": False}


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, Exception):
        return False


def check_policy(password: str, policy: dict | None = None) -> list[str]:
    p = {**DEFAULT_POLICY, **(policy or {})}
    problems = []
    if len(password) < p["min_length"]:
        problems.append(f"at least {p['min_length']} characters")
    if p["require_upper"] and not re.search(r"[A-Z]", password):
        problems.append("an upper-case letter")
    if p["require_lower"] and not re.search(r"[a-z]", password):
        problems.append("a lower-case letter")
    if p["require_digit"] and not re.search(r"\d", password):
        problems.append("a digit")
    if p["require_symbol"] and not re.search(r"[^A-Za-z0-9]", password):
        problems.append("a symbol")
    return problems


def new_session_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, token_hash(token)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def expiry(hours: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)
