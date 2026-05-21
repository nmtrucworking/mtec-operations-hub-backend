from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.evaluation_constants import (
    EVIDENCE_STATUSES_APPROVAL,
    EVIDENCE_STATUSES_DRAFT,
)
from app.models import EvaluationCriterion, EvaluationEvidence, EvaluationScoreEvent
from app.services.evaluation_errors import EvaluationEvidenceError


class EvidenceValidationService:
    def __init__(self, db: Session):
        self.db = db

    def _valid_statuses(self, mode: str) -> set[str]:
        if mode == "approval":
            return EVIDENCE_STATUSES_APPROVAL
        return EVIDENCE_STATUSES_DRAFT

    def count_evidence_for_event(self, score_event_id: str, *, mode: str = "draft") -> int:
        statuses = self._valid_statuses(mode)
        return (
            self.db.scalar(
                select(func.count())
                .select_from(EvaluationEvidence)
                .where(
                    EvaluationEvidence.score_event_id == score_event_id,
                    EvaluationEvidence.status.in_(statuses),
                )
            )
            or 0
        )

    def has_valid_evidence_for_event(
        self, score_event_id: str, *, mode: str = "draft"
    ) -> bool:
        return self.count_evidence_for_event(score_event_id, mode=mode) > 0

    def validate_score_events(
        self,
        events: Iterable[EvaluationScoreEvent],
        *,
        strict: bool = True,
        mode: str = "draft",
    ) -> list[dict]:
        warnings: list[dict] = []
        criteria_cache: dict[str, EvaluationCriterion | None] = {}

        for event in events:
            criterion = criteria_cache.get(event.criterion_id)
            if event.criterion_id not in criteria_cache:
                criterion = self.db.get(EvaluationCriterion, event.criterion_id)
                criteria_cache[event.criterion_id] = criterion

            if criterion is None or not criterion.requires_evidence:
                continue

            if event.id and self.has_valid_evidence_for_event(event.id, mode=mode):
                continue

            warnings.append(
                {
                    "code": "MISSING_REQUIRED_EVIDENCE",
                    "scoreEventId": event.id,
                    "criterionId": event.criterion_id,
                    "criterionCode": event.criterion_code,
                    "mode": mode,
                }
            )

        if strict and warnings:
            raise EvaluationEvidenceError(
                f"{len(warnings)} score event(s) are missing required evidence"
            )

        return warnings
