import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import create_audit_log
from app.models import EvaluationCriterion, User

DEFAULT_CRITERIA_EFFECTIVE_FROM = date(2026, 1, 1)
DEFAULT_CRITERIA_DATA_PATH = (
    Path(__file__).resolve().parent.parent
    / "templates"
    / "evaluations"
    / "default_criteria_2026.json"
)


def _load_default_criteria_2026() -> list[dict[str, Any]]:
    with DEFAULT_CRITERIA_DATA_PATH.open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError("Default evaluation criteria seed data must be a list")
    return data


DEFAULT_EVALUATION_CRITERIA_2026: list[dict[str, Any]] = (
    _load_default_criteria_2026()
)


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
                    effective_to=payload.get("effective_to"),
                    description=payload.get("description"),
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
                criterion.effective_to = payload.get("effective_to")
                criterion.description = payload.get("description")
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
        return json.dumps(metadata, ensure_ascii=False, sort_keys=True)
