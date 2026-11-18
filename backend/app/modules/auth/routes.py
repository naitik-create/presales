from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.audit import audit
from app.core.deps import SESSION_COOKIE, CurrentUser, get_current_user
from app.core.security import check_policy, expiry, hash_password, new_session_token, token_hash, verify_password
from app.core.settings_store import get_setting
from app.db import get_db, utcnow
from app.models.core import Notification, User, UserSession

router = APIRouter(prefix="/auth", tags=["auth"])

NAV = [
    ("dashboard", "Dashboard", "/"),
    ("rfp", "RFP Intelligence", "/rfp"),
    ("demo", "Demo Intelligence", "/demo"),
    ("ask", "Ask Motadata", "/ask"),
    ("scorecard", "Team Scorecard", "/scorecard"),
    ("knowledge", "Knowledge Hub", "/knowledge"),
    ("admin", "Administration", "/admin"),
]


def can_see_scorecard(cu: CurrentUser) -> bool:
    manager = cu.has_any("scoring.view_all", "scoring.approve", "scoring.manage_rules", "scoring.view_reports",
                         "scoring.propose")
    return manager or (cu.user.is_scoring_participant and cu.has("scoring.view_own"))


def nav_visible(cu: CurrentUser, key: str) -> bool:
    return {
        "dashboard": True,
        "rfp": cu.has_area("rfp") or cu.has_area("submitted"),
        "demo": cu.has_area("demo") or cu.has_area("usecases"),
        "ask": cu.has_area("ask"),
        "scorecard": can_see_scorecard(cu),
        "knowledge": cu.has_area("knowledge"),
        "admin": cu.has_area("admin"),
    }[key]


class LoginIn(BaseModel):
    username: str
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


def me_payload(cu: CurrentUser) -> dict:
    u = cu.user
    nav = [{"key": k, "label": label, "href": href} for k, label, href in NAV if nav_visible(cu, k)]
    return {
        "id": u.id, "username": u.username, "full_name": u.full_name, "email": u.email,
        "must_change_password": u.must_change_password, "is_scoring_participant": u.is_scoring_participant,
        "roles": [r.name for r in u.roles], "permissions": sorted(cu.perms), "nav": nav,
    }


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    sess_cfg = get_setting(db, "session")
    user = db.scalar(select(User).where(User.username == body.username.strip().lower()))
    now = datetime.now(timezone.utc)
    if user and user.locked_until and user.locked_until > now:
        raise HTTPException(423, "Account locked after repeated failed sign-ins. Try again later.")
    if not user or not user.is_active or not verify_password(user.password_hash, body.password):
        if user:
            user.failed_logins += 1
            if user.failed_logins >= sess_cfg["max_login_attempts"]:
                user.locked_until = now + timedelta(minutes=sess_cfg["lockout_minutes"])
                user.failed_logins = 0
                audit(db, user, "auth.locked", "user", user.id)
            audit(db, None, "auth.login_failed", "user", user.id, username=body.username)
            db.commit()
        raise HTTPException(401, "Incorrect username or password")
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    token, th = new_session_token()
    db.add(UserSession(token_hash=th, user_id=user.id, expires_at=expiry(sess_cfg["hours"]),
                       ip=request.client.host if request.client else ""))
    db.execute(delete(UserSession).where(UserSession.expires_at < now))
    audit(db, user, "auth.login", "user", user.id)
    db.commit()
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=sess_cfg["hours"] * 3600,
                        secure=get_settings().APP_ENV == "production" and request.url.scheme == "https", path="/")
    return me_payload(CurrentUser(user))


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.execute(delete(UserSession).where(UserSession.token_hash == token_hash(token)))
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(cu: CurrentUser = Depends(get_current_user)):
    return me_payload(cu)


@router.post("/change-password")
def change_password(body: ChangePasswordIn, cu: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.get(User, cu.id)
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(400, "Current password is incorrect")
    problems = check_policy(body.new_password, get_setting(db, "password_policy"))
    if problems:
        raise HTTPException(400, "Password must contain " + ", ".join(problems))
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    audit(db, user, "auth.password_changed", "user", user.id)
    db.commit()
    return {"ok": True}


@router.get("/notifications")
def notifications(cu: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Notification).where(Notification.user_id == cu.id)
                      .order_by(Notification.at.desc()).limit(50)).all()
    return [{"id": n.id, "at": n.at, "kind": n.kind, "title": n.title, "body": n.body, "link": n.link, "read": n.read}
            for n in rows]


@router.post("/notifications/read")
def mark_read(cu: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.user_id == cu.id, Notification.read.is_(False))
               .values(read=True))
    db.commit()
    return {"ok": True, "at": utcnow()}
