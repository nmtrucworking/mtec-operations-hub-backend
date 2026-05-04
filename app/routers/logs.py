from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session
import csv
import io
import json
from fastapi.responses import StreamingResponse
from datetime import datetime

from app.db import get_db
from app.deps import get_current_user
from app.models import AuditLog, User
from app.core.response import api_response
from app.utils import sanitize_pagination

router = APIRouter(prefix="/logs", tags=["logs"])

def _parse_snapshot(value: str | None) -> dict | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except Exception:
        return None

def _log_out(log: AuditLog, actor_name: str | None) -> dict:
    return {
        "id": log.id,
        "actorId": log.actor_user_id,
        "actorName": actor_name or "System",
        "action": log.action,
        "module": log.resource_type.upper(),
        "resourceId": log.resource_id,
        "beforeSnapshot": _parse_snapshot(log.before_snapshot),
        "afterSnapshot": _parse_snapshot(log.after_snapshot),
        "createdAt": log.created_at,
    }

def _apply_filters(stmt, count_stmt, search, module, action):
    if search:
        pattern = f"%{search}%"
        # Since we don't have actor name in AuditLog table directly, 
        # we might need to join with User if we want to search by actor name.
        # For now, let's search in resource_id and action.
        stmt = stmt.where(or_(AuditLog.resource_id.ilike(pattern), AuditLog.action.ilike(pattern)))
        count_stmt = count_stmt.where(or_(AuditLog.resource_id.ilike(pattern), AuditLog.action.ilike(pattern)))
    
    if module:
        module_key = module.strip().lower()
        module_map = {
            "member": "member",
            "members": "member",
            "user": "user",
            "users": "user",
            "request": "request",
            "requests": "request",
            "transaction": "transaction",
            "transactions": "transaction",
            "finance": "transaction",
            "asset": "asset",
            "assets": "asset",
            "logistics": "asset",
            "discipline": "discipline",
            "settings": "settings",
            "auth": "auth",
        }
        resource_type = module_map.get(module_key, module_key)
        stmt = stmt.where(AuditLog.resource_type == resource_type)
        count_stmt = count_stmt.where(AuditLog.resource_type == resource_type)
        
    if action:
        action_key = action.strip().upper()
        if action_key == "PASSWORD_CHANGE":
            action_key = "CHANGE_PASSWORD"

        if action_key in {"CREATE", "UPDATE", "DELETE", "REVIEW"}:
            pattern = f"{action_key}_%"
            stmt = stmt.where(AuditLog.action.ilike(pattern))
            count_stmt = count_stmt.where(AuditLog.action.ilike(pattern))
        else:
            stmt = stmt.where(AuditLog.action == action_key)
            count_stmt = count_stmt.where(AuditLog.action == action_key)
        
    return stmt, count_stmt

@router.get("")
def list_logs(
    search: str | None = None,
    module: str | None = None,
    action: str | None = None,
    page: int = Query(default=1),
    pageSize: int = Query(default=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    # Authorization: BCN and BCM can view logs
    if current_user.role not in {"bcn", "bcm"}:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Khong co quyen xem nhat ky")

    page, pageSize = sanitize_pagination(page, pageSize)
    
    stmt = select(AuditLog, User.full_name).outerjoin(User, AuditLog.actor_user_id == User.id).order_by(AuditLog.created_at.desc())
    count_stmt = select(func.count()).select_from(AuditLog)
    
    stmt, count_stmt = _apply_filters(stmt, count_stmt, search, module, action)
    
    total = db.scalar(count_stmt) or 0
    results = db.execute(stmt.offset((page - 1) * pageSize).limit(pageSize)).all()
    
    data = []
    for log, actor_name in results:
        data.append(_log_out(log, actor_name))
        
    return api_response(
        data=data,
        meta={"page": page, "pageSize": pageSize, "total": total}
    )

@router.get("/export")
def export_logs(
    search: str | None = None,
    module: str | None = None,
    action: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Authorization: BCN and BCM can export logs
    if current_user.role not in {"bcn", "bcm"}:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Khong co quyen xuat nhat ky")

    stmt = select(AuditLog, User.full_name).outerjoin(User, AuditLog.actor_user_id == User.id).order_by(AuditLog.created_at.desc())
    count_stmt = select(func.count()).select_from(AuditLog)
    
    stmt, count_stmt = _apply_filters(stmt, count_stmt, search, module, action)
    
    results = db.execute(stmt).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Actor", "Action", "Module", "Resource ID", "Created At"])
    
    for log, actor_name in results:
        writer.writerow([
            log.id,
            actor_name or "System",
            log.action,
            log.resource_type.upper(),
            log.resource_id,
            log.created_at.isoformat()
        ])
    
    output.seek(0)
    filename = f"audit_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
