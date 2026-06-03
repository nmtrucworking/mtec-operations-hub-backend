from collections.abc import Iterable

from sqlalchemy import and_, func, or_, select, union_all
from sqlalchemy.orm import Session

from app.core.evaluation_constants import (
    EVIDENCE_STATUSES_APPROVAL,
    EVIDENCE_STATUSES_DRAFT,
)
from app.models import (
    EvaluationCriterion,
    EvaluationEvidence,
    EvaluationEvidenceAppliedEvent,
    EvaluationScoreEvent,
)
from app.services.evaluation_errors import EvaluationEvidenceError


class EvidenceValidationService:
    def __init__(self, db: Session):
        self.db = db

    def _valid_statuses(self, mode: str) -> set[str]:
        if mode == "approval":
            return EVIDENCE_STATUSES_APPROVAL
        return EVIDENCE_STATUSES_DRAFT

    def count_evidence_for_event(self, score_event_id: str, *, mode: str = "draft") -> int:
        return self.count_evidence_for_events([score_event_id], mode=mode).get(score_event_id, 0)

    def count_evidence_for_events(
        self, score_event_ids: Iterable[str], *, mode: str = "draft"
    ) -> dict[str, int]:
        event_ids = [event_id for event_id in score_event_ids if event_id]
        if not event_ids:
            return {}

        statuses = self._valid_statuses(mode)

        direct_pairs = select(
            EvaluationEvidence.id.label("evidence_id"),
            EvaluationEvidence.score_event_id.label("score_event_id"),
        ).where(
            EvaluationEvidence.score_event_id.in_(event_ids),
            EvaluationEvidence.status.in_(statuses),
        )
        applied_pairs = select(
            EvaluationEvidenceAppliedEvent.evidence_id.label("evidence_id"),
            EvaluationEvidenceAppliedEvent.score_event_id.label("score_event_id"),
        ).join(
            EvaluationEvidence,
            EvaluationEvidence.id == EvaluationEvidenceAppliedEvent.evidence_id,
        ).where(
            EvaluationEvidenceAppliedEvent.score_event_id.in_(event_ids),
            EvaluationEvidence.status.in_(statuses),
        )
        combined = union_all(direct_pairs, applied_pairs).subquery("combined")
        pair_rows = self.db.execute(
            select(
                combined.c.score_event_id,
                func.count(func.distinct(combined.c.evidence_id)).label("evidence_count"),
            )
            .select_from(combined)
            .group_by(combined.c.score_event_id)
        ).all()

        return {
            row.score_event_id: int(row.evidence_count or 0)
            for row in pair_rows
            if row.score_event_id
        }

    def count_effective_evidence_for_event(
        self,
        event: EvaluationScoreEvent,
        *,
        mode: str = "draft",
    ) -> int:
        statuses = self._valid_statuses(mode)
        direct_count = self.count_evidence_for_event(event.id, mode=mode)
        if not event.criterion_id:
            return direct_count

        criterion_level_count = self.db.scalar(
            select(func.count())
            .select_from(EvaluationEvidence)
            .where(
                EvaluationEvidence.cycle_id == event.cycle_id,
                EvaluationEvidence.member_id == event.member_id,
                EvaluationEvidence.criterion_id == event.criterion_id,
                EvaluationEvidence.score_event_id.is_(None),
                ~EvaluationEvidence.applied_events.any(),
                EvaluationEvidence.status.in_(statuses),
            )
        ) or 0
        return int(direct_count) + int(criterion_level_count)

    def count_effective_evidence_for_events(
        self,
        events: Iterable[EvaluationScoreEvent],
        *,
        mode: str = "draft",
    ) -> dict[str, int]:
        events_list = [event for event in events if event.id]
        if not events_list:
            return {}

        statuses = self._valid_statuses(mode)
        counts = self.count_evidence_for_events((event.id for event in events_list), mode=mode)
        events_by_key: dict[tuple[str, str, str], list[str]] = {}
        cycle_ids = {event.cycle_id for event in events_list}
        member_ids = {event.member_id for event in events_list}
        criterion_ids = {event.criterion_id for event in events_list if event.criterion_id}
        for event in events_list:
            if event.criterion_id:
                events_by_key.setdefault((event.cycle_id, event.member_id, event.criterion_id), []).append(event.id)

        if not criterion_ids:
            return counts

        criterion_rows = self.db.execute(
            select(
                EvaluationEvidence.cycle_id,
                EvaluationEvidence.member_id,
                EvaluationEvidence.criterion_id,
                func.count(func.distinct(EvaluationEvidence.id)).label("evidence_count"),
            )
            .where(
                EvaluationEvidence.cycle_id.in_(cycle_ids),
                EvaluationEvidence.member_id.in_(member_ids),
                EvaluationEvidence.criterion_id.in_(criterion_ids),
                EvaluationEvidence.score_event_id.is_(None),
                ~EvaluationEvidence.applied_events.any(),
                EvaluationEvidence.status.in_(statuses),
            )
            .group_by(
                EvaluationEvidence.cycle_id,
                EvaluationEvidence.member_id,
                EvaluationEvidence.criterion_id,
            )
        ).all()

        for row in criterion_rows:
            key = (row.cycle_id, row.member_id, row.criterion_id)
            event_ids = events_by_key.get(key, [])
            if not event_ids:
                continue
            criterion_count = int(row.evidence_count or 0)
            for event_id in event_ids:
                counts[event_id] = counts.get(event_id, 0) + criterion_count

        return counts

    def has_valid_evidence_for_event(
        self, score_event_id: str, *, mode: str = "draft"
    ) -> bool:
        event = self.db.get(EvaluationScoreEvent, score_event_id)
        if not event:
            return False
        return self.count_effective_evidence_for_event(event, mode=mode) > 0

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
            evidence_count_by_event_id = self.count_effective_evidence_for_events(
                events_list, mode=mode
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
