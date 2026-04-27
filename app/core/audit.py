import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog, User


def _serialize_snapshot(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=True, default=str)


def create_audit_log(
    db: Session,
    action: str,
    resource_type: str,
    resource_id: str,
    actor: User | None = None,
    before_snapshot: dict[str, Any] | None = None,
    after_snapshot: dict[str, Any] | None = None,
) -> None:
    log = AuditLog(
        actor_user_id=actor.id if actor else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        before_snapshot=_serialize_snapshot(before_snapshot),
        after_snapshot=_serialize_snapshot(after_snapshot),
    )
    db.add(log)
