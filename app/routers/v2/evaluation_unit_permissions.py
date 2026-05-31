from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.core.audit import create_audit_log
from app.services.evaluation_unit_permission_service import EvaluationUnitPermissionService
from app.schemas_evaluation import (
    UserUnitPermissionCreate,
    UserUnitPermissionUpdate,
)

router = APIRouter(prefix="/evaluations/unit-permissions", tags=["evaluations"])


def _require_any_role(user: User, roles: set[str]) -> None:
    if not user.has_any_roles(roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": "FORBIDDEN", "message": "Permission denied"})


@router.get("")
def list_permissions(
    userId: str | None = Query(default=None),
    unitCode: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_any_role(current_user, {"bcn", "bvh_hr", "bvh_discipline"})
    svc = EvaluationUnitPermissionService(db)
    rows = svc.list_permissions(user_id=userId, unit_code=unitCode)
    data = [
        {
            "id": r.id,
            "userId": r.user_id,
            "unitCode": r.unit_code,
            "permissionRole": r.permission_role,
            "canViewUnitResults": r.can_view_unit_results,
            "canScoreComponentIi": r.can_score_component_ii,
            "canScoreComponentIiiA": r.can_score_component_iii_a,
            "canScoreComponentIiiB": r.can_score_component_iii_b,
            "canSubmitEvidence": r.can_submit_evidence,
            "canVerifyEvidence": r.can_verify_evidence,
            "canReviewAppeal": r.can_review_appeal,
            "isActive": r.is_active,
            "startsAt": r.starts_at,
            "endsAt": r.ends_at,
            "createdAt": r.created_at,
            "updatedAt": r.updated_at,
        }
        for r in rows
    ]
    return {"data": data}


@router.post("")
def create_permission(
    body: UserUnitPermissionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_any_role(current_user, {"bcn", "bvh_hr"})
    svc = EvaluationUnitPermissionService(db)
    obj = svc.create(body.model_dump())
    create_audit_log(db=db, action="CREATE_USER_UNIT_PERMISSION", resource_type="user_unit_permission", resource_id=obj.id, actor=current_user, after_snapshot={"userId": obj.user_id, "unitCode": obj.unit_code})
    db.commit()
    db.refresh(obj)
    return {"data": {"id": obj.id}}


@router.patch("/{permission_id}")
def update_permission(
    permission_id: str,
    body: UserUnitPermissionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_any_role(current_user, {"bcn", "bvh_hr"})
    svc = EvaluationUnitPermissionService(db)
    before = svc.get(permission_id)
    if not before:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "RESOURCE_NOT_FOUND", "message": "Permission not found"})
    obj = svc.update(permission_id, body.model_dump(exclude_unset=True))
    create_audit_log(db=db, action="UPDATE_USER_UNIT_PERMISSION", resource_type="user_unit_permission", resource_id=obj.id, actor=current_user, before_snapshot={"userId": before.user_id, "unitCode": before.unit_code}, after_snapshot={"userId": obj.user_id, "unitCode": obj.unit_code})
    db.commit()
    db.refresh(obj)
    return {"data": {"id": obj.id}}


@router.delete("/{permission_id}")
def delete_permission(
    permission_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_any_role(current_user, {"bcn"})
    svc = EvaluationUnitPermissionService(db)
    before = svc.get(permission_id)
    if not before:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "RESOURCE_NOT_FOUND", "message": "Permission not found"})
    svc.delete(permission_id)
    create_audit_log(db=db, action="DELETE_USER_UNIT_PERMISSION", resource_type="user_unit_permission", resource_id=permission_id, actor=current_user, before_snapshot={"userId": before.user_id, "unitCode": before.unit_code})
    db.commit()
    return {"data": {"deleted": True, "id": permission_id}}
