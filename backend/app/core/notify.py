from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import Notification, Permission, Role, User, role_permissions, user_roles


def notify(db: Session, user_id: int, kind: str, title: str, body: str = "", link: str = "") -> None:
    db.add(Notification(user_id=user_id, kind=kind, title=title, body=body, link=link))


def users_with_permission(db: Session, code: str) -> list[int]:
    q = (select(User.id).join(user_roles, user_roles.c.user_id == User.id)
         .join(role_permissions, role_permissions.c.role_id == user_roles.c.role_id)
         .where(role_permissions.c.permission_code == code, User.is_active.is_(True)).distinct())
    return list(db.scalars(q))


def notify_permission(db: Session, code: str, kind: str, title: str, body: str = "", link: str = "") -> None:
    for uid in users_with_permission(db, code):
        notify(db, uid, kind, title, body, link)


__all__ = ["notify", "notify_permission", "users_with_permission", "Permission", "Role"]
