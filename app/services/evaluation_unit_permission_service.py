from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import list

from app.models import UserUnitPermission


class EvaluationUnitPermissionService:
    def __init__(self, db: Session):
        self.db = db

    def list_permissions(self, *, user_id: str | None = None, unit_code: str | None = None) -> list[UserUnitPermission]:
        stmt = select(UserUnitPermission)
        if user_id:
            stmt = stmt.where(UserUnitPermission.user_id == user_id)
        if unit_code:
            stmt = stmt.where(UserUnitPermission.unit_code == unit_code)
        return self.db.scalars(stmt).all()

    def get(self, permission_id: str) -> UserUnitPermission | None:
        return self.db.get(UserUnitPermission, permission_id)

    def create(self, payload: dict) -> UserUnitPermission:
        obj = UserUnitPermission(
            user_id=payload["userId"],
            unit_code=payload["unitCode"],
            permission_role=payload["permissionRole"],
            can_view_unit_results=payload.get("canViewUnitResults", False),
            can_score_component_ii=payload.get("canScoreComponentIi", False),
            can_score_component_iii_a=payload.get("canScoreComponentIiiA", False),
            can_score_component_iii_b=payload.get("canScoreComponentIiiB", False),
            can_submit_evidence=payload.get("canSubmitEvidence", True),
            can_verify_evidence=payload.get("canVerifyEvidence", False),
            can_review_appeal=payload.get("canReviewAppeal", False),
        )
        self.db.add(obj)
        self.db.flush()
        return obj

    def update(self, permission_id: str, payload: dict) -> UserUnitPermission:
        obj = self.get(permission_id)
        if not obj:
            return None
        mapping = {
            "unitCode": "unit_code",
            "permissionRole": "permission_role",
            "canViewUnitResults": "can_view_unit_results",
            "canScoreComponentIi": "can_score_component_ii",
            "canScoreComponentIiiA": "can_score_component_iii_a",
            "canScoreComponentIiiB": "can_score_component_iii_b",
            "canSubmitEvidence": "can_submit_evidence",
            "canVerifyEvidence": "can_verify_evidence",
            "canReviewAppeal": "can_review_appeal",
            "isActive": "is_active",
        }
        for key, value in payload.items():
            if key in mapping and value is not None:
                setattr(obj, mapping[key], value)
        self.db.add(obj)
        self.db.flush()
        return obj

    def delete(self, permission_id: str) -> bool:
        obj = self.get(permission_id)
        if not obj:
            return False
        self.db.delete(obj)
        self.db.flush()
        return True
