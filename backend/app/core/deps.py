from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import token_hash
from app.db import get_db
from app.models.core import User, UserSession

SESSION_COOKIE = "mp_session"


class CurrentUser:
    def __init__(self, user: User):
        self.user = user
        self.perms = user.permission_codes()

    @property
    def id(self) -> int:
        return self.user.id

    def has(self, code: str) -> bool:
        return code in self.perms

    def has_any(self, *codes: str) -> bool:
        return any(c in self.perms for c in codes)

    def has_area(self, area: str) -> bool:
        return any(p.startswith(area + ".") for p in self.perms)

    def section_keys(self) -> set[str]:
        return {p.split(".", 2)[2] for p in self.perms if p.startswith("knowledge.view.")}


def get_current_user(request: Request, db: Session = Depends(get_db)) -> CurrentUser:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(401, "Not signed in")
    s = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(token)))
    if not s or s.expires_at < datetime.now(timezone.utc):
        raise HTTPException(401, "Session expired. Please sign in again.")
    user = db.get(User, s.user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "Account is not active")
    return CurrentUser(user)


def require(*codes: str):
    """Allow the request if the user holds any of the given permission codes. Enforced on every endpoint."""
    def dep(cu: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not cu.has_any(*codes):
            raise HTTPException(403, "You do not have permission for this action")
        return cu
    return dep


def require_area(area: str):
    def dep(cu: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not cu.has_area(area):
            raise HTTPException(403, "You do not have permission for this area")
        return cu
    return dep
