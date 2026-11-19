import re
import secrets
from datetime import date, datetime, time, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.client import month_key, month_spend
from app.ai.embeddings import OPTIONS
from app.core.audit import audit
from app.core.deps import CurrentUser, get_current_user, require
from app.core.jobs import enqueue
from app.core.secrets import PROVIDERS, get_secret, set_secret, source_of
from app.core.security import check_policy, hash_password
from app.core.settings_store import get_setting, set_setting
from app.db import get_db
from app.models.ai import AgentConfiguration, AIModel, AIUsageLog, Budget, EmbeddingConfiguration, ModelPrice
from app.models.core import ApiCredential, AuditLog, Job, Permission, Role, User, UserSession, user_roles

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------- users ----------
class UserIn(BaseModel):
    username: str
    full_name: str
    email: str = ""
    role_ids: list[int] = []
    is_scoring_participant: bool = False
    password: str | None = None


class UserPatch(BaseModel):
    full_name: str | None = None
    email: str | None = None
    role_ids: list[int] | None = None
    is_active: bool | None = None
    is_scoring_participant: bool | None = None


def user_out(u: User) -> dict:
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "email": u.email, "is_active": u.is_active,
            "is_scoring_participant": u.is_scoring_participant, "roles": [{"id": r.id, "name": r.name} for r in u.roles],
            "last_login_at": u.last_login_at, "locked": bool(u.locked_until and u.locked_until > datetime.now(timezone.utc))}


def _temp_password() -> str:
    return "Mp-" + secrets.token_urlsafe(9) + "7a"


@router.get("/users")
def list_users(cu: CurrentUser = Depends(require("admin.users")), db: Session = Depends(get_db)):
    return [user_out(u) for u in db.scalars(select(User).order_by(User.username))]


@router.post("/users")
def create_user(body: UserIn, cu: CurrentUser = Depends(require("admin.users")), db: Session = Depends(get_db)):
    username = body.username.strip().lower()
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(400, "Username already exists")
    pw = body.password or _temp_password()
    problems = check_policy(pw, get_setting(db, "password_policy"))
    if problems:
        raise HTTPException(400, "Password must contain " + ", ".join(problems))
    u = User(username=username, full_name=body.full_name, email=body.email, password_hash=hash_password(pw),
             is_scoring_participant=body.is_scoring_participant, must_change_password=True)
    u.roles = list(db.scalars(select(Role).where(Role.id.in_(body.role_ids)))) if body.role_ids else []
    db.add(u)
    db.flush()
    audit(db, cu.user, "user.created", "user", u.id, username=username, roles=[r.name for r in u.roles])
    db.commit()
    return {**user_out(u), "temporary_password": pw}


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserPatch, cu: CurrentUser = Depends(require("admin.users")), db: Session = Depends(get_db)):
    u = db.get(User, user_id) or _404()
    changes = body.model_dump(exclude_none=True)
    if body.role_ids is not None:
        before = [r.name for r in u.roles]
        u.roles = list(db.scalars(select(Role).where(Role.id.in_(body.role_ids))))
        audit(db, cu.user, "user.roles_changed", "user", u.id, before=before, after=[r.name for r in u.roles])
    for k in ("full_name", "email", "is_active", "is_scoring_participant"):
        if k in changes:
            setattr(u, k, changes[k])
    if body.is_active is False:
        db.query(UserSession).filter(UserSession.user_id == u.id).delete()
    audit(db, cu.user, "user.updated", "user", u.id, **{k: v for k, v in changes.items() if k != "role_ids"})
    db.commit()
    return user_out(u)


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, cu: CurrentUser = Depends(require("admin.users")), db: Session = Depends(get_db)):
    u = db.get(User, user_id) or _404()
    pw = _temp_password()
    u.password_hash = hash_password(pw)
    u.must_change_password = True
    u.locked_until = None
    u.failed_logins = 0
    db.query(UserSession).filter(UserSession.user_id == u.id).delete()
    audit(db, cu.user, "user.password_reset", "user", u.id)
    db.commit()
    return {"temporary_password": pw}


# ---------- roles & permissions ----------
class RoleIn(BaseModel):
    name: str
    description: str = ""
    permissions: list[str] = []


@router.get("/permissions")
def list_permissions(cu: CurrentUser = Depends(require("admin.roles", "admin.users")), db: Session = Depends(get_db)):
    return [{"code": p.code, "area": p.area, "label": p.label} for p in db.scalars(select(Permission).order_by(Permission.code))]


@router.get("/roles")
def list_roles(cu: CurrentUser = Depends(require("admin.roles", "admin.users")), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(user_roles.c.role_id, func.count()).join(User, User.id == user_roles.c.user_id)
                             .where(User.is_active.is_(True)).group_by(user_roles.c.role_id)).all())
    return [{"id": r.id, "name": r.name, "description": r.description, "is_system": r.is_system,
             "permissions": sorted(p.code for p in r.permissions), "user_count": counts.get(r.id, 0)}
            for r in db.scalars(select(Role).order_by(Role.name))]


def _apply_role(db: Session, role: Role, body: RoleIn) -> None:
    perms = list(db.scalars(select(Permission).where(Permission.code.in_(body.permissions))))
    unknown = set(body.permissions) - {p.code for p in perms}
    if unknown:
        raise HTTPException(400, f"Unknown permissions: {', '.join(sorted(unknown))}")
    role.name, role.description, role.permissions = body.name, body.description, perms


@router.post("/roles")
def create_role(body: RoleIn, cu: CurrentUser = Depends(require("admin.roles")), db: Session = Depends(get_db)):
    if db.scalar(select(Role).where(Role.name == body.name)):
        raise HTTPException(400, "A role with this name exists")
    role = Role()
    _apply_role(db, role, body)
    db.add(role)
    db.flush()
    audit(db, cu.user, "role.created", "role", role.id, name=role.name, permissions=body.permissions)
    db.commit()
    return {"id": role.id}


@router.put("/roles/{role_id}")
def update_role(role_id: int, body: RoleIn, cu: CurrentUser = Depends(require("admin.roles")), db: Session = Depends(get_db)):
    role = db.get(Role, role_id) or _404()
    before = sorted(p.code for p in role.permissions)
    _apply_role(db, role, body)
    audit(db, cu.user, "role.permissions_changed", "role", role.id, name=role.name, before=before,
          after=sorted(body.permissions))
    db.commit()
    return {"ok": True}


@router.delete("/roles/{role_id}")
def delete_role(role_id: int, cu: CurrentUser = Depends(require("admin.roles")), db: Session = Depends(get_db)):
    role = db.get(Role, role_id) or _404()
    if role.is_system:
        raise HTTPException(400, "Default roles cannot be deleted; edit their permissions instead")
    audit(db, cu.user, "role.deleted", "role", role.id, name=role.name)
    db.delete(role)
    db.commit()
    return {"ok": True}


# ---------- AI configuration ----------
class AgentPatch(BaseModel):
    model_id: str | None = None
    max_output_tokens: int | None = None
    effort: str | None = None
    timeout_seconds: int | None = None
    max_retries: int | None = None
    enabled: bool | None = None


class ModelIn(BaseModel):
    model_id: str
    label: str
    provider: str = "anthropic"
    endpoint: str = ""
    input_per_mtok: Decimal = Decimal(0)
    output_per_mtok: Decimal = Decimal(0)
    active: bool = True


@router.get("/ai/agents")
def list_agents(cu: CurrentUser = Depends(require("admin.ai_config")), db: Session = Depends(get_db)):
    return [{"agent_key": a.agent_key, "label": a.label, "module": a.module, "model_id": a.model_id,
             "max_output_tokens": a.max_output_tokens, "effort": a.effort, "timeout_seconds": a.timeout_seconds,
             "max_retries": a.max_retries, "enabled": a.enabled}
            for a in db.scalars(select(AgentConfiguration).order_by(AgentConfiguration.module, AgentConfiguration.label))]


@router.patch("/ai/agents/{agent_key}")
def update_agent(agent_key: str, body: AgentPatch, cu: CurrentUser = Depends(require("admin.ai_config")),
                 db: Session = Depends(get_db)):
    a = db.scalar(select(AgentConfiguration).where(AgentConfiguration.agent_key == agent_key)) or _404()
    changes = body.model_dump(exclude_none=True)
    if body.effort and body.effort not in ("low", "medium", "high", "xhigh", "max"):
        raise HTTPException(400, "Effort must be low, medium, high, xhigh or max")
    if body.max_output_tokens is not None and not 256 <= body.max_output_tokens <= 128000:
        raise HTTPException(400, "Maximum output tokens must be between 256 and 128000")
    before = {k: getattr(a, k) for k in changes}
    for k, v in changes.items():
        setattr(a, k, v)
    audit(db, cu.user, "ai.agent_changed", "agent", agent_key, before=before, after=changes)
    db.commit()
    return {"ok": True}


MODEL_PROVIDERS = ("anthropic", "openai", "google", "azure_openai")


@router.get("/ai/models")
def list_models(cu: CurrentUser = Depends(require("admin.ai_config", "admin.usage")), db: Session = Depends(get_db)):
    prices = {p.model_id: p for p in db.scalars(select(ModelPrice))}
    return [{"model_id": m.model_id, "label": m.label, "active": m.active, "provider": m.provider, "endpoint": m.endpoint,
             "input_per_mtok": prices.get(m.model_id).input_per_mtok if m.model_id in prices else 0,
             "output_per_mtok": prices.get(m.model_id).output_per_mtok if m.model_id in prices else 0}
            for m in db.scalars(select(AIModel).order_by(AIModel.label))]


@router.put("/ai/models")
def upsert_model(body: ModelIn, cu: CurrentUser = Depends(require("admin.ai_config")), db: Session = Depends(get_db)):
    if body.provider not in MODEL_PROVIDERS:
        raise HTTPException(400, "Provider must be one of: " + ", ".join(MODEL_PROVIDERS))
    if body.provider == "azure_openai" and not body.endpoint.startswith("https://"):
        raise HTTPException(400, "Azure OpenAI models need the resource endpoint, e.g. https://myresource.openai.azure.com")
    m = db.scalar(select(AIModel).where(AIModel.model_id == body.model_id))
    if not m:
        m = AIModel(model_id=body.model_id, label=body.label)
        db.add(m)
    m.label, m.active, m.provider, m.endpoint = body.label, body.active, body.provider, body.endpoint.strip()
    p = db.scalar(select(ModelPrice).where(ModelPrice.model_id == body.model_id))
    if not p:
        p = ModelPrice(model_id=body.model_id)
        db.add(p)
    p.input_per_mtok, p.output_per_mtok = body.input_per_mtok, body.output_per_mtok
    audit(db, cu.user, "ai.model_price_changed", "model", body.model_id, input=str(body.input_per_mtok),
          output=str(body.output_per_mtok), active=body.active)
    db.commit()
    return {"ok": True}


@router.get("/ai/embedding")
def get_embedding(cu: CurrentUser = Depends(require("admin.ai_config")), db: Session = Depends(get_db)):
    rows = db.scalars(select(EmbeddingConfiguration).order_by(EmbeddingConfiguration.id)).all()
    pending = [r for r in rows if r.pending_activation]
    job = db.get(Job, pending[0].reindex_job_id) if pending and pending[0].reindex_job_id else None
    return {"options": OPTIONS, "configurations": [
        {"id": r.id, "provider": r.provider, "model_name": r.model_name, "dimension": r.dimension,
         "is_active": r.is_active, "pending_activation": r.pending_activation} for r in rows],
        "reindex_job": {"id": job.id, "status": job.status, "progress": job.progress, "message": job.message} if job else None}


class EmbeddingSwitch(BaseModel):
    provider: str
    confirm: bool = False


@router.post("/ai/embedding/switch")
def switch_embedding(body: EmbeddingSwitch, cu: CurrentUser = Depends(require("admin.ai_config")), db: Session = Depends(get_db)):
    if body.provider not in OPTIONS:
        raise HTTPException(400, "Unknown embedding option")
    if not body.confirm:
        raise HTTPException(400, "Switching the embedding model re-indexes every document. Confirm to continue.")
    active = db.scalar(select(EmbeddingConfiguration).where(EmbeddingConfiguration.is_active.is_(True)))
    opt = OPTIONS[body.provider]
    if active and active.provider == body.provider:
        raise HTTPException(400, "This option is already active")
    target = db.scalar(select(EmbeddingConfiguration).where(EmbeddingConfiguration.provider == body.provider))
    if not target:
        target = EmbeddingConfiguration(provider=body.provider, model_name=opt["model_name"], dimension=opt["dimension"])
        db.add(target)
        db.flush()
    target.pending_activation = True
    job = enqueue(db, "knowledge.reindex", {"config_id": target.id}, user_id=cu.id, timeout_seconds=6 * 3600)
    target.reindex_job_id = job.id
    audit(db, cu.user, "ai.embedding_switch_started", "embedding", target.id, provider=body.provider,
          model=target.model_name, previous=active.model_name if active else None)
    db.commit()
    return {"job_id": job.id}


# ---------- API keys (stored encrypted) ----------
class ApiKeyIn(BaseModel):
    value: str
    label: str = ""


def _key_out(db: Session, provider: str, row: ApiCredential | None) -> dict:
    meta = PROVIDERS.get(provider, {"label": row.label if row else provider, "used_for": "Custom key; not used by any feature yet"})
    return {"provider": provider, "label": (row.label if row and row.label else meta["label"]), "used_for": meta["used_for"],
            "source": source_of(db, provider), "masked": f"…{row.last4}" if row else "",
            "updated_at": row.updated_at if row else None, "last_tested_at": row.last_tested_at if row else None,
            "last_test_ok": row.last_test_ok if row else None, "last_test_message": row.last_test_message if row else "",
            "testable": provider in ("anthropic", "voyage", "openai", "google"), "custom": provider not in PROVIDERS}


@router.get("/api-keys")
def list_api_keys(cu: CurrentUser = Depends(require("admin.api_keys")), db: Session = Depends(get_db)):
    rows = {r.provider: r for r in db.scalars(select(ApiCredential))}
    providers = list(PROVIDERS) + sorted(p for p in rows if p not in PROVIDERS)
    return [_key_out(db, p, rows.get(p)) for p in providers]


@router.put("/api-keys/{provider}")
def save_api_key(provider: str, body: ApiKeyIn, cu: CurrentUser = Depends(require("admin.api_keys")), db: Session = Depends(get_db)):
    if provider not in PROVIDERS and not re.fullmatch(r"[a-z0-9_]{2,40}", provider):
        raise HTTPException(400, "Provider name must be 2-40 lower-case letters, digits or underscores")
    value = body.value.strip()
    if len(value) < 8 or len(value) > 4000 or any(ch.isspace() for ch in value):
        raise HTTPException(400, "This does not look like an API key")
    prefix = PROVIDERS.get(provider, {}).get("prefix")
    if prefix and not value.startswith(prefix):
        raise HTTPException(400, f"{PROVIDERS[provider]['label']} keys start with '{prefix}'")
    row = set_secret(db, provider, value, cu.id, body.label)
    audit(db, cu.user, "api_key.saved", "api_key", provider, last4=value[-4:])  # never the value itself
    db.commit()
    return _key_out(db, provider, row)


@router.delete("/api-keys/{provider}")
def delete_api_key(provider: str, cu: CurrentUser = Depends(require("admin.api_keys")), db: Session = Depends(get_db)):
    row = db.scalar(select(ApiCredential).where(ApiCredential.provider == provider)) or _404()
    db.delete(row)
    audit(db, cu.user, "api_key.deleted", "api_key", provider)
    db.commit()
    return {"ok": True}


@router.post("/api-keys/{provider}/test")
def test_api_key(provider: str, cu: CurrentUser = Depends(require("admin.api_keys")), db: Session = Depends(get_db)):
    key = get_secret(db, provider)
    if not key:
        raise HTTPException(400, "No key is configured for this provider")
    ok, message = False, ""
    try:
        if provider == "anthropic":
            import anthropic
            models = anthropic.Anthropic(api_key=key, max_retries=0, timeout=20).models.list(limit=5)
            ok, message = True, "Connected. Models available: " + ", ".join(m.id for m in models.data)
        elif provider == "voyage":
            import httpx
            r = httpx.post("https://api.voyageai.com/v1/embeddings", timeout=20, headers={"Authorization": f"Bearer {key}"},
                           json={"input": ["connection test"], "model": "voyage-3"})
            ok, message = r.status_code == 200, "Connected" if r.status_code == 200 else f"HTTP {r.status_code}: {r.text[:200]}"
        elif provider in ("openai", "google"):
            from app.ai.providers import test_key
            ok, message = True, test_key(provider, key)
        else:
            raise HTTPException(400, "No connection test is available for this provider")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        ok, message = False, str(e)[:300].replace(key, "***")
    row = db.scalar(select(ApiCredential).where(ApiCredential.provider == provider))
    if row:
        row.last_tested_at, row.last_test_ok, row.last_test_message = datetime.now(timezone.utc), ok, message
    audit(db, cu.user, "api_key.tested", "api_key", provider, ok=ok)
    db.commit()
    return {"ok": ok, "message": message}


# ---------- usage & budget ----------
def _usage_filter(q, start: date | None, end: date | None, user_id, module, agent, job_id):
    if start:
        q = q.where(AIUsageLog.at >= datetime.combine(start, time.min, tzinfo=timezone.utc))
    if end:
        q = q.where(AIUsageLog.at <= datetime.combine(end, time.max, tzinfo=timezone.utc))
    if user_id:
        q = q.where(AIUsageLog.user_id == user_id)
    if module:
        q = q.where(AIUsageLog.module == module)
    if agent:
        q = q.where(AIUsageLog.agent_key == agent)
    if job_id:
        q = q.where(AIUsageLog.job_id == job_id)
    return q


@router.get("/usage")
def usage(start: date | None = None, end: date | None = None, user_id: int | None = None, module: str | None = None,
          agent: str | None = None, job_id: int | None = None,
          cu: CurrentUser = Depends(require("admin.usage")), db: Session = Depends(get_db)):
    agg = (func.count(AIUsageLog.id), func.coalesce(func.sum(AIUsageLog.input_tokens), 0),
           func.coalesce(func.sum(AIUsageLog.output_tokens), 0), func.coalesce(func.sum(AIUsageLog.estimated_cost), 0))
    totals = db.execute(_usage_filter(select(*agg), start, end, user_id, module, agent, job_id)).one()

    def grouped(col, label_map=None):
        rows = db.execute(_usage_filter(select(col, *agg), start, end, user_id, module, agent, job_id).group_by(col)
                          .order_by(agg[3].desc())).all()
        return [{"key": (label_map or {}).get(r[0], r[0]), "id": r[0], "calls": r[1], "input_tokens": r[2],
                 "output_tokens": r[3], "cost": float(r[4])} for r in rows]

    users = {u.id: u.full_name for u in db.scalars(select(User))}
    day = func.date_trunc("day", AIUsageLog.at)
    daily = db.execute(_usage_filter(select(day, func.count(AIUsageLog.id), func.coalesce(func.sum(AIUsageLog.estimated_cost), 0)),
                                     start, end, user_id, module, agent, job_id).group_by(day).order_by(day)).all()
    recent = db.scalars(_usage_filter(select(AIUsageLog), start, end, user_id, module, agent, job_id)
                        .order_by(AIUsageLog.at.desc()).limit(200)).all()
    b = db.scalar(select(Budget).where(Budget.month == month_key()))
    spent = float(month_spend(db))
    return {
        "totals": {"calls": totals[0], "input_tokens": totals[1], "output_tokens": totals[2], "cost": float(totals[3])},
        "by_day": [{"day": d.date().isoformat(), "calls": n, "cost": float(c)} for d, n, c in daily],
        "by_user": grouped(AIUsageLog.user_id, users), "by_module": grouped(AIUsageLog.module),
        "by_agent": grouped(AIUsageLog.agent_key), "by_model": grouped(AIUsageLog.model_id),
        "recent": [{"at": r.at, "user": users.get(r.user_id, "system"), "module": r.module, "agent": r.agent_key,
                    "model": r.model_id, "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
                    "duration_ms": r.duration_ms, "status": r.status, "job_id": r.job_id, "ref": f"{r.ref_type}:{r.ref_id}" if r.ref_type else "",
                    "cost": float(r.estimated_cost)} for r in recent],
        "budget": {"month": month_key(), "amount": float(b.amount) if b else None, "spent": spent,
                   "remaining": float(b.amount) - spent if b else None, "thresholds": b.thresholds if b else [80, 100],
                   "hard_stop": b.hard_stop if b else False},
    }


class BudgetIn(BaseModel):
    amount: Decimal
    thresholds: list[int] = [80, 100]
    hard_stop: bool = False


@router.put("/budget")
def set_budget(body: BudgetIn, cu: CurrentUser = Depends(require("admin.budget")), db: Session = Depends(get_db)):
    b = db.scalar(select(Budget).where(Budget.month == month_key()))
    if not b:
        b = Budget(month=month_key(), amount=body.amount)
        db.add(b)
    before = {"amount": str(b.amount), "hard_stop": b.hard_stop}
    b.amount, b.thresholds, b.hard_stop = body.amount, sorted(body.thresholds), body.hard_stop
    b.notified = [t for t in (b.notified or []) if t in body.thresholds and month_spend(db) >= body.amount * t / 100]
    audit(db, cu.user, "budget.changed", "budget", b.month, before=before,
          after={"amount": str(body.amount), "thresholds": body.thresholds, "hard_stop": body.hard_stop})
    db.commit()
    return {"ok": True}


# ---------- settings ----------
EDITABLE_SETTINGS = ("rfp_limits", "password_policy", "session", "url_fetch_allowed_domains", "retrieval")


@router.get("/settings")
def get_settings_(cu: CurrentUser = Depends(require("admin.settings")), db: Session = Depends(get_db)):
    return {k: get_setting(db, k) for k in EDITABLE_SETTINGS}


@router.put("/settings/{key}")
def put_setting(key: str, value: dict | list, cu: CurrentUser = Depends(require("admin.settings")), db: Session = Depends(get_db)):
    if key not in EDITABLE_SETTINGS:
        raise HTTPException(404, "Unknown setting")
    before = get_setting(db, key)
    set_setting(db, key, value)
    audit(db, cu.user, "settings.changed", "setting", key, before=before, after=value)
    db.commit()
    return get_setting(db, key)


# ---------- audit ----------
@router.get("/audit")
def audit_log(action: str | None = None, actor: str | None = None, entity: str | None = None,
              start: date | None = None, end: date | None = None, limit: int = Query(200, le=1000), offset: int = 0,
              cu: CurrentUser = Depends(require("admin.audit")), db: Session = Depends(get_db)):
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action.ilike(f"%{action}%"))
    if actor:
        q = q.where(AuditLog.actor_name.ilike(f"%{actor}%"))
    if entity:
        q = q.where(AuditLog.entity == entity)
    if start:
        q = q.where(AuditLog.at >= datetime.combine(start, time.min, tzinfo=timezone.utc))
    if end:
        q = q.where(AuditLog.at <= datetime.combine(end, time.max, tzinfo=timezone.utc))
    # Scoring audit entries are visible only to scoring managers
    if not cu.has("scoring.view_all"):
        q = q.where(~AuditLog.action.startswith("scoring."))
    rows = db.scalars(q.order_by(AuditLog.id.desc()).limit(limit).offset(offset)).all()
    return [{"id": r.id, "at": r.at, "actor": r.actor_name, "action": r.action, "entity": r.entity,
             "entity_id": r.entity_id, "details": r.details} for r in rows]


# ---------- jobs ----------
@router.get("/jobs")
def jobs(status: str | None = None, cu: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(Job)
    if not cu.has_any("admin.settings", "rfp.cancel_jobs"):
        q = q.where(Job.created_by == cu.id)
    if status:
        q = q.where(Job.status == status)
    return [job_out(j) for j in db.scalars(q.order_by(Job.id.desc()).limit(100))]


def job_out(j: Job) -> dict:
    return {"id": j.id, "kind": j.kind, "queue": j.queue, "status": j.status, "progress": j.progress,
            "message": j.message, "error": j.error.split("\n")[0] if j.error else "", "attempts": j.attempts,
            "created_at": j.created_at, "started_at": j.started_at, "finished_at": j.finished_at,
            "ref_type": j.ref_type, "ref_id": j.ref_id}


@router.get("/jobs/{job_id}")
def job(job_id: int, cu: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    j = db.get(Job, job_id) or _404()
    if j.created_by != cu.id and not cu.has_any("admin.settings", "rfp.cancel_jobs", "rfp.view"):
        raise HTTPException(403, "Not allowed")
    return job_out(j)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, cu: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    j = db.get(Job, job_id) or _404()
    if j.created_by != cu.id and not cu.has_any("admin.settings", "rfp.cancel_jobs"):
        raise HTTPException(403, "Not allowed")
    if j.status == "Queued":
        j.status = "Cancelled"
        j.finished_at = datetime.now(timezone.utc)
    elif j.status == "Processing":
        j.cancel_requested = True
    else:
        raise HTTPException(400, f"Job is already {j.status}")
    audit(db, cu.user, "job.cancelled", "job", j.id, kind=j.kind)
    db.commit()
    return job_out(j)


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: int, cu: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    j = db.get(Job, job_id) or _404()
    if j.created_by != cu.id and not cu.has_any("admin.settings", "rfp.cancel_jobs"):
        raise HTTPException(403, "Not allowed")
    if j.status not in ("Failed", "Cancelled"):
        raise HTTPException(400, "Only failed or cancelled jobs can be retried")
    j.status, j.attempts, j.error, j.cancel_requested, j.progress = "Queued", 0, "", False, 0
    j.run_after = datetime.now(timezone.utc)
    audit(db, cu.user, "job.retried", "job", j.id, kind=j.kind)
    db.commit()
    return job_out(j)


def _404():
    raise HTTPException(404, "Not found")
