from sqlalchemy.orm import Session

from app.models.core import AuditLog, User


def audit(db: Session, actor: User | None, action: str, entity: str = "", entity_id: object = "", **details) -> None:
    """Add an audit record to the current transaction. The caller commits."""
    db.add(AuditLog(
        actor_id=actor.id if actor else None,
        actor_name=actor.username if actor else "system",
        action=action,
        entity=entity,
        entity_id=str(entity_id) if entity_id is not None else "",
        details=details,
    ))
