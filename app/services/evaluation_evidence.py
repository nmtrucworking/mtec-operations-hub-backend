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

    def count_evidence_for_events(
        self, score_event_ids: Iterable[str], *, mode: str = "draft"
    ) -> dict[str, int]:
        event_ids = [event_id for event_id in score_event_ids if event_id]
        if not event_ids:
            return {}

        statuses = self._valid_statuses(mode)
        rows = self.db.execute(
            select(
                EvaluationEvidence.score_event_id,
                func.count().label("evidence_count"),
            )
            .where(
                EvaluationEvidence.score_event_id.in_(event_ids),
                EvaluationEvidence.status.in_(statuses),
            )
            .group_by(EvaluationEvidence.score_event_id)
        ).all()

        return {
            row.score_event_id: int(row.evidence_count or 0)
            for row in rows
            if row.score_event_id
        }

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
        evidence_count_by_event_id: dict[str, int] | None = None,
        criteria: list[EvaluationCriterion] | None = None,
    ) -> list[dict]:
        events_list = list(events)
        warnings: list[dict] = []
        criteria_cache: dict[str, EvaluationCriterion | None] = {}
        if criteria:
            criteria_cache = {c.id: c for c in criteria}

        if evidence_count_by_event_id is None:
            evidence_count_by_event_id = self.count_evidence_for_events(
                (event.id for event in events_list if event.id), mode=mode
            )

        for event in events_list:
            criterion = criteria_cache.get(event.criterion_id)
            if event.criterion_id not in criteria_cache:
                criterion = self.db.get(EvaluationCriterion, event.criterion_id)
                criteria_cache[event.criterion_id] = criterion

            if criterion is None or not criterion.requires_evidence:
                continue

            if event.id and evidence_count_by_event_id.get(event.id, 0) > 0:
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
