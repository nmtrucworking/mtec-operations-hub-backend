import json
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import create_audit_log
from app.core.evaluation_constants import (
    COMPONENT_I,
    COMPONENT_II,
    COMPONENT_III_A,
)
from app.models import EvaluationCriterion, User

DEFAULT_CRITERIA_EFFECTIVE_FROM = date(2026, 1, 1)

DEFAULT_EVALUATION_CRITERIA_2026: list[dict[str, Any]] = [
    {
        "code": "I.1",
        "name": "Ty le tham gia sinh hoat, hop va hoat dong bat buoc",
        "component": COMPONENT_I,
        "unit_scope": "ALL",
        "unit_code": None,
        "max_score": 15.0,
        "score_method": "RATIO",
        "requires_evidence": True,
        "sort_order": 101,
        "metadata": {"formula": "attendance_rate * 15"},
    },
    {
        "code": "I.2",
        "name": "Tuan thu quy trinh xin phep va bao cao vang mat",
        "component": COMPONENT_I,
        "unit_scope": "ALL",
        "unit_code": None,
        "max_score": 7.0,
        "score_method": "DEDUCTIVE",
        "requires_evidence": True,
        "sort_order": 102,
        "metadata": {"source": "attendance"},
    },
    {
        "code": "I.3",
        "name": "Dung gio va tuan thu thoi han phan hoi",
        "component": COMPONENT_I,
        "unit_scope": "ALL",
        "unit_code": None,
        "max_score": 4.0,
        "score_method": "DEDUCTIVE",
        "requires_evidence": True,
        "sort_order": 103,
    },
    {
        "code": "I.4",
        "name": "Hoan thanh nghia vu hanh chinh bat buoc",
        "component": COMPONENT_I,
        "unit_scope": "ALL",
        "unit_code": None,
        "max_score": 4.0,
        "score_method": "MANUAL",
        "requires_evidence": True,
        "sort_order": 104,
    },
    {
        "code": "II.1",
        "name": "Tinh than trach nhiem trong cong viec",
        "component": COMPONENT_II,
        "unit_scope": "ALL",
        "unit_code": None,
        "max_score": 5.0,
        "score_method": "MANUAL",
        "requires_evidence": True,
        "sort_order": 201,
    },
    {
        "code": "II.2",
        "name": "Muc do chu dong va phoi hop to chuc",
        "component": COMPONENT_II,
        "unit_scope": "ALL",
        "unit_code": None,
        "max_score": 5.0,
        "score_method": "MANUAL",
        "requires_evidence": True,
        "sort_order": 202,
    },
    {
        "code": "II.3",
        "name": "Bao ve uy tin, hinh anh va chuan muc phat ngon cua CLB",
        "component": COMPONENT_II,
        "unit_scope": "ALL",
        "unit_code": None,
        "max_score": 5.0,
        "score_method": "MANUAL",
        "requires_evidence": True,
        "sort_order": 203,
    },
    {
        "code": "II.4",
        "name": "Bao mat tai nguyen so va thong tin noi bo",
        "component": COMPONENT_II,
        "unit_scope": "ALL",
        "unit_code": None,
        "max_score": 5.0,
        "score_method": "MANUAL",
        "requires_evidence": True,
        "sort_order": 204,
    },
    {
        "code": "III-A.1",
        "name": "Hoan thanh nhiem vu duoc phan cong",
        "component": COMPONENT_III_A,
        "unit_scope": "ALL",
        "unit_code": None,
        "max_score": 10.0,
        "score_method": "MANUAL",
        "requires_evidence": True,
        "sort_order": 301,
    },
    {
        "code": "III-A.2",
        "name": "Chat luong san pham dau ra",
        "component": COMPONENT_III_A,
        "unit_scope": "ALL",
        "unit_code": None,
        "max_score": 8.0,
        "score_method": "MANUAL",
        "requires_evidence": True,
        "sort_order": 302,
    },
    {
        "code": "III-A.3",
        "name": "Tien do va kha nang cap nhat cong viec",
        "component": COMPONENT_III_A,
        "unit_scope": "ALL",
        "unit_code": None,
        "max_score": 5.0,
        "score_method": "MANUAL",
        "requires_evidence": True,
        "sort_order": 303,
    },
    {
        "code": "III-A.4",
        "name": "Kha nang phoi hop trong nhiem vu chuyen mon",
        "component": COMPONENT_III_A,
        "unit_scope": "ALL",
        "unit_code": None,
        "max_score": 4.0,
        "score_method": "MANUAL",
        "requires_evidence": True,
        "sort_order": 304,
    },
    {
        "code": "III-A.5",
        "name": "Cai tien, hoc hoi va dong gop chuyen mon",
        "component": COMPONENT_III_A,
        "unit_scope": "ALL",
        "unit_code": None,
        "max_score": 3.0,
        "score_method": "ADDITIVE",
        "requires_evidence": True,
        "sort_order": 305,
    },
]


class EvaluationCriteriaSeedService:
    def __init__(self, db: Session):
        self.db = db

    def seed_default_criteria_2026(
        self,
        *,
        effective_from: date = DEFAULT_CRITERIA_EFFECTIVE_FROM,
        actor_user_id: str | None = None,
    ) -> dict:
        inserted = 0
        updated = 0

        for payload in DEFAULT_EVALUATION_CRITERIA_2026:
            criterion = self._find_existing(
                code=payload["code"],
                unit_code=payload["unit_code"],
                effective_from=effective_from,
            )
            if criterion is None:
                criterion = EvaluationCriterion(
                    code=payload["code"],
                    name=payload["name"],
                    component=payload["component"],
                    unit_scope=payload["unit_scope"],
                    unit_code=payload["unit_code"],
                    max_score=payload["max_score"],
                    score_method=payload["score_method"],
                    requires_evidence=payload["requires_evidence"],
                    is_active=True,
                    sort_order=payload["sort_order"],
                    effective_from=effective_from,
                    metadata_json=self._metadata_json(payload),
                )
                self.db.add(criterion)
                inserted += 1
            else:
                criterion.name = payload["name"]
                criterion.component = payload["component"]
                criterion.unit_scope = payload["unit_scope"]
                criterion.max_score = payload["max_score"]
                criterion.score_method = payload["score_method"]
                criterion.requires_evidence = payload["requires_evidence"]
                criterion.is_active = True
                criterion.sort_order = payload["sort_order"]
                criterion.metadata_json = self._metadata_json(payload)
                updated += 1

        actor = self.db.get(User, actor_user_id) if actor_user_id else None
        create_audit_log(
            db=self.db,
            action="SEED_EVALUATION_CRITERIA",
            resource_type="evaluation_criteria",
            resource_id="default-2026",
            actor=actor,
            after_snapshot={"inserted": inserted, "updated": updated},
        )
        self.db.flush()

        return {
            "insertedCount": inserted,
            "updatedCount": updated,
            "effectiveFrom": effective_from.isoformat(),
        }

    def _find_existing(
        self, *, code: str, unit_code: str | None, effective_from: date
    ) -> EvaluationCriterion | None:
        stmt = select(EvaluationCriterion).where(
            EvaluationCriterion.code == code,
            EvaluationCriterion.effective_from == effective_from,
        )
        if unit_code is None:
            stmt = stmt.where(EvaluationCriterion.unit_code.is_(None))
        else:
            stmt = stmt.where(EvaluationCriterion.unit_code == unit_code)
        return self.db.scalar(stmt)

    def _metadata_json(self, payload: dict[str, Any]) -> str | None:
        metadata = payload.get("metadata")
        if not metadata:
            return None
        return json.dumps(metadata, ensure_ascii=True, sort_keys=True)
