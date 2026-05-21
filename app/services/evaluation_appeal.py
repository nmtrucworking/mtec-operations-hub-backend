from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import create_audit_log
from app.core.evaluation_constants import (
    APPEAL_OPEN_STATUSES,
    APPEAL_RESOLVED_STATUSES,
    APPEAL_STATUS_ACCEPTED,
    APPEAL_STATUS_CANCELLED,
    APPEAL_STATUS_IN_REVIEW,
    APPEAL_STATUS_NEEDS_MORE_EVIDENCE,
    APPEAL_STATUS_PARTIALLY_ACCEPTED,
    APPEAL_STATUS_PENDING,
    APPEAL_STATUS_REJECTED,
    CYCLE_STATUS_APPEAL_RESOLUTION,
    CYCLE_STATUS_MEMBER_REVIEW,
    CYCLE_STATUS_READY_FOR_APPROVAL,
    EVENT_TYPE_OVERRIDE,
    MEMBER_EVALUATION_STATUS_APPEAL_RESOLVED,
    MEMBER_EVALUATION_STATUS_APPEALED,
    SOURCE_TYPE_APPEAL,
)
from app.models import (
    EvaluationAppeal,
    EvaluationCriterion,
    EvaluationCycle,
    EvaluationScoreEvent,
    Member,
    MemberEvaluation,
    User,
)
from app.services.evaluation_calculator import EvaluationCalculatorService
from app.services.evaluation_errors import (
    EvaluationAppealAlreadyResolvedError,
    EvaluationAppealNotFoundError,
    EvaluationInvalidStatusTransitionError,
    EvaluationMissingCriteriaError,
    EvaluationNotFoundError,
    EvaluationReviewWindowClosedError,
)
from app.services.evaluation_notification import EvaluationNotificationService
from app.services.evaluation_workflow_utils import (
    ensure_cycle_is_mutable,
    metadata_dump,
    metadata_load,
    utcnow,
)

RESOLVE_DECISIONS = {
    APPEAL_STATUS_ACCEPTED,
    APPEAL_STATUS_PARTIALLY_ACCEPTED,
    APPEAL_STATUS_REJECTED,
}


class EvaluationAppealService:
    def __init__(self, db: Session):
        self.db = db
        self.notifications = EvaluationNotificationService()

    def create_appeal(
        self,
        cycle_id: str,
        body: dict,
        *,
        actor_user_id: str,
        allow_late: bool = False,
    ) -> EvaluationAppeal:
        cycle = self._get_cycle(cycle_id)
        ensure_cycle_is_mutable(cycle)
        if cycle.status not in {CYCLE_STATUS_MEMBER_REVIEW, CYCLE_STATUS_APPEAL_RESOLUTION}:
            raise EvaluationInvalidStatusTransitionError(
                f"Appeal cannot be created while cycle is {cycle.status}"
            )
        if not allow_late and self._review_deadline_passed(cycle):
            raise EvaluationReviewWindowClosedError(
                f"Review window is closed for cycle {cycle_id}"
            )

        member = self.db.get(Member, body["memberId"])
        if not member:
            raise EvaluationNotFoundError(f"Member not found: {body['memberId']}")

        member_evaluation_id = body.get("memberEvaluationId")
        if not member_evaluation_id:
            member_evaluation = self._get_member_evaluation(cycle_id, body["memberId"])
            member_evaluation_id = member_evaluation.id if member_evaluation else None

        metadata = metadata_load(body.get("metadataJson"))
        if body.get("metadata"):
            metadata.update(body["metadata"])
        metadata["evidenceIds"] = body.get("evidenceIds", [])
        metadata["createdByUserId"] = actor_user_id

        appeal = EvaluationAppeal(
            cycle_id=cycle_id,
            member_id=body["memberId"],
            member_evaluation_id=member_evaluation_id,
            criterion_id=body.get("criterionId"),
            criterion_code=body.get("criterionCode"),
            appeal_type=body["appealType"],
            content=body["content"],
            requested_score=body.get("requestedScore"),
            metadata_json=metadata_dump(metadata),
        )
        self.db.add(appeal)
        self.db.flush()

        self._set_member_status(cycle_id, body["memberId"], MEMBER_EVALUATION_STATUS_APPEALED)

        self._audit(
            actor_user_id=actor_user_id,
            action="CREATE_EVALUATION_APPEAL",
            resource_id=appeal.id,
            after_snapshot={
                "cycleId": cycle_id,
                "memberId": appeal.member_id,
                "status": appeal.status,
            },
        )
        self.notifications.notify(
            "evaluation.appeal.created",
            {"cycleId": cycle_id, "appealId": appeal.id, "memberId": appeal.member_id},
        )
        self.db.flush()
        return appeal

    def start_review(self, appeal_id: str, *, actor_user_id: str) -> EvaluationAppeal:
        appeal = self._get_appeal(appeal_id)
        self._ensure_appeal_mutable(appeal)
        if appeal.status not in {APPEAL_STATUS_PENDING, APPEAL_STATUS_NEEDS_MORE_EVIDENCE}:
            raise EvaluationInvalidStatusTransitionError(
                f"Cannot start review from appeal status {appeal.status}"
            )
        before_status = appeal.status
        appeal.status = APPEAL_STATUS_IN_REVIEW
        self._append_history(
            appeal,
            {
                "action": "START_REVIEW",
                "actorUserId": actor_user_id,
                "fromStatus": before_status,
                "toStatus": appeal.status,
                "at": utcnow(),
            },
        )
        self._audit(
            actor_user_id=actor_user_id,
            action="START_EVALUATION_APPEAL_REVIEW",
            resource_id=appeal.id,
            before_snapshot={"status": before_status},
            after_snapshot={"status": appeal.status},
        )
        self.db.flush()
        return appeal

    def request_more_evidence(
        self,
        appeal_id: str,
        note: str,
        *,
        actor_user_id: str,
    ) -> EvaluationAppeal:
        appeal = self._get_appeal(appeal_id)
        self._ensure_appeal_mutable(appeal)
        if appeal.status not in {APPEAL_STATUS_PENDING, APPEAL_STATUS_IN_REVIEW}:
            raise EvaluationInvalidStatusTransitionError(
                f"Cannot request evidence from appeal status {appeal.status}"
            )
        before_status = appeal.status
        appeal.status = APPEAL_STATUS_NEEDS_MORE_EVIDENCE
        appeal.resolution_note = note
        self._append_history(
            appeal,
            {
                "action": "REQUEST_EVIDENCE",
                "actorUserId": actor_user_id,
                "fromStatus": before_status,
                "toStatus": appeal.status,
                "note": note,
                "at": utcnow(),
            },
        )
        self._audit(
            actor_user_id=actor_user_id,
            action="REQUEST_APPEAL_EVIDENCE",
            resource_id=appeal.id,
            before_snapshot={"status": before_status},
            after_snapshot={"status": appeal.status, "note": note},
        )
        self.notifications.notify(
            "evaluation.appeal.evidence_requested",
            {"cycleId": appeal.cycle_id, "appealId": appeal.id, "memberId": appeal.member_id},
        )
        self.db.flush()
        return appeal

    def resolve_appeal(
        self,
        appeal_id: str,
        body: dict,
        *,
        actor_user_id: str,
    ) -> dict:
        appeal = self._get_appeal(appeal_id)
        self._ensure_appeal_mutable(appeal)
        decision = body["decision"]
        if decision not in RESOLVE_DECISIONS:
            raise EvaluationInvalidStatusTransitionError(f"Invalid appeal decision {decision}")
        if body.get("createAdjustmentEvent") and decision == APPEAL_STATUS_REJECTED:
            raise EvaluationInvalidStatusTransitionError(
                "Rejected appeal cannot create adjustment event"
            )

        cycle = self._get_cycle(appeal.cycle_id)
        ensure_cycle_is_mutable(cycle)
        before_status = appeal.status
        created_adjustment_event = None
        if body.get("createAdjustmentEvent"):
            created_adjustment_event = self._create_adjustment_event(
                appeal,
                body,
                actor_user_id=actor_user_id,
            )

        appeal.status = decision
        appeal.resolution_note = body["resolutionNote"]
        appeal.resolved_by_user_id = actor_user_id
        appeal.resolved_at = utcnow()
        self._append_history(
            appeal,
            {
                "action": "RESOLVE",
                "actorUserId": actor_user_id,
                "fromStatus": before_status,
                "toStatus": appeal.status,
                "decision": decision,
                "adjustmentEventId": (
                    created_adjustment_event.id if created_adjustment_event else None
                ),
                "at": appeal.resolved_at,
            },
        )

        recomputed = None
        if body.get("recomputeMember", True) and created_adjustment_event is not None:
            recomputed = EvaluationCalculatorService(self.db).compute_member(
                appeal.cycle_id,
                appeal.member_id,
                actor_user_id=actor_user_id,
                strict=False,
                evidence_mode="draft",
            )

        self._refresh_member_and_cycle_status(appeal.cycle_id, appeal.member_id)
        self._audit(
            actor_user_id=actor_user_id,
            action="RESOLVE_EVALUATION_APPEAL",
            resource_id=appeal.id,
            before_snapshot={"status": before_status},
            after_snapshot={
                "status": appeal.status,
                "decision": decision,
                "adjustmentEventId": (
                    created_adjustment_event.id if created_adjustment_event else None
                ),
            },
        )
        self.notifications.notify(
            "evaluation.appeal.resolved",
            {
                "cycleId": appeal.cycle_id,
                "appealId": appeal.id,
                "memberId": appeal.member_id,
                "status": appeal.status,
            },
        )
        self.db.flush()
        return {
            "appeal": appeal,
            "adjustmentEvent": created_adjustment_event,
            "recomputed": recomputed,
        }

    def cancel_appeal(
        self,
        appeal_id: str,
        reason: str | None,
        *,
        actor_user_id: str,
    ) -> EvaluationAppeal:
        appeal = self._get_appeal(appeal_id)
        self._ensure_appeal_mutable(appeal)
        before_status = appeal.status
        appeal.status = APPEAL_STATUS_CANCELLED
        appeal.resolution_note = reason
        appeal.resolved_by_user_id = actor_user_id
        appeal.resolved_at = utcnow()
        self._append_history(
            appeal,
            {
                "action": "CANCEL",
                "actorUserId": actor_user_id,
                "fromStatus": before_status,
                "toStatus": appeal.status,
                "reason": reason,
                "at": appeal.resolved_at,
            },
        )
        self._refresh_member_and_cycle_status(appeal.cycle_id, appeal.member_id)
        self._audit(
            actor_user_id=actor_user_id,
            action="CANCEL_EVALUATION_APPEAL",
            resource_id=appeal.id,
            before_snapshot={"status": before_status},
            after_snapshot={"status": appeal.status, "reason": reason},
        )
        self.notifications.notify(
            "evaluation.appeal.cancelled",
            {"cycleId": appeal.cycle_id, "appealId": appeal.id, "memberId": appeal.member_id},
        )
        self.db.flush()
        return appeal

    def _create_adjustment_event(
        self,
        appeal: EvaluationAppeal,
        body: dict,
        *,
        actor_user_id: str,
    ) -> EvaluationScoreEvent:
        if body.get("adjustedScoreDelta") is None:
            raise EvaluationInvalidStatusTransitionError(
                "adjustedScoreDelta is required for adjustment event"
            )
        criterion = self._find_adjustment_criterion(appeal, body)
        existing = self.db.scalar(
            select(EvaluationScoreEvent).where(
                EvaluationScoreEvent.cycle_id == appeal.cycle_id,
                EvaluationScoreEvent.member_id == appeal.member_id,
                EvaluationScoreEvent.criterion_code == criterion.code,
                EvaluationScoreEvent.source_type == SOURCE_TYPE_APPEAL,
                EvaluationScoreEvent.source_id == appeal.id,
                EvaluationScoreEvent.event_type == EVENT_TYPE_OVERRIDE,
                EvaluationScoreEvent.is_void.is_(False),
            )
        )
        if existing:
            return existing

        event = EvaluationScoreEvent(
            cycle_id=appeal.cycle_id,
            member_id=appeal.member_id,
            criterion_id=criterion.id,
            criterion_code=criterion.code,
            component=criterion.component,
            unit_code=criterion.unit_code,
            event_type=EVENT_TYPE_OVERRIDE,
            source_type=SOURCE_TYPE_APPEAL,
            source_id=appeal.id,
            raw_value=appeal.requested_score,
            score_delta=body["adjustedScoreDelta"],
            max_score_snapshot=criterion.max_score,
            note=body["resolutionNote"],
            recorded_by_user_id=actor_user_id,
            metadata_json=metadata_dump(
                {
                    "appealId": appeal.id,
                    "decision": body["decision"],
                    "evidenceIds": body.get("evidenceIds", []),
                }
            ),
        )
        self.db.add(event)
        self.db.flush()
        self._audit(
            actor_user_id=actor_user_id,
            action="CREATE_APPEAL_ADJUSTMENT_EVENT",
            resource_id=event.id,
            resource_type="evaluation_score_event",
            after_snapshot={
                "appealId": appeal.id,
                "scoreDelta": event.score_delta,
                "criterionCode": event.criterion_code,
            },
        )
        return event

    def _find_adjustment_criterion(
        self,
        appeal: EvaluationAppeal,
        body: dict,
    ) -> EvaluationCriterion:
        criterion = None
        target_code = body.get("targetCriterionCode") or appeal.criterion_code
        if appeal.criterion_id:
            criterion = self.db.get(EvaluationCriterion, appeal.criterion_id)
        if criterion is None and target_code:
            criterion = self.db.scalar(
                select(EvaluationCriterion).where(
                    EvaluationCriterion.code == target_code,
                    EvaluationCriterion.is_active.is_(True),
                )
            )
        if not criterion:
            raise EvaluationMissingCriteriaError(
                "Adjustment event requires targetCriterionCode or criterionId"
            )
        return criterion

    def _refresh_member_and_cycle_status(self, cycle_id: str, member_id: str) -> None:
        open_for_member = self._count_open_appeals(cycle_id, member_id=member_id)
        self._set_member_status(
            cycle_id,
            member_id,
            MEMBER_EVALUATION_STATUS_APPEALED
            if open_for_member
            else MEMBER_EVALUATION_STATUS_APPEAL_RESOLVED,
        )
        cycle = self._get_cycle(cycle_id)
        if (
            cycle.status == CYCLE_STATUS_APPEAL_RESOLUTION
            and self._count_open_appeals(cycle_id) == 0
        ):
            cycle.status = CYCLE_STATUS_READY_FOR_APPROVAL

    def _get_cycle(self, cycle_id: str) -> EvaluationCycle:
        cycle = self.db.get(EvaluationCycle, cycle_id)
        if not cycle:
            raise EvaluationNotFoundError(f"Evaluation cycle not found: {cycle_id}")
        return cycle

    def _get_appeal(self, appeal_id: str) -> EvaluationAppeal:
        appeal = self.db.get(EvaluationAppeal, appeal_id)
        if not appeal:
            raise EvaluationAppealNotFoundError(f"Appeal not found: {appeal_id}")
        return appeal

    def _ensure_appeal_mutable(self, appeal: EvaluationAppeal) -> None:
        if appeal.status in APPEAL_RESOLVED_STATUSES:
            raise EvaluationAppealAlreadyResolvedError(
                f"Appeal already resolved: {appeal.id}"
            )

    def _get_member_evaluation(
        self,
        cycle_id: str,
        member_id: str,
    ) -> MemberEvaluation | None:
        return self.db.scalar(
            select(MemberEvaluation).where(
                MemberEvaluation.cycle_id == cycle_id,
                MemberEvaluation.member_id == member_id,
            )
        )

    def _set_member_status(self, cycle_id: str, member_id: str, next_status: str) -> None:
        member_evaluation = self._get_member_evaluation(cycle_id, member_id)
        if member_evaluation:
            member_evaluation.status = next_status

    def _count_open_appeals(self, cycle_id: str, *, member_id: str | None = None) -> int:
        stmt = (
            select(func.count())
            .select_from(EvaluationAppeal)
            .where(
                EvaluationAppeal.cycle_id == cycle_id,
                EvaluationAppeal.status.in_(APPEAL_OPEN_STATUSES),
            )
        )
        if member_id:
            stmt = stmt.where(EvaluationAppeal.member_id == member_id)
        return self.db.scalar(stmt) or 0

    def _review_deadline_passed(self, cycle: EvaluationCycle) -> bool:
        metadata = metadata_load(cycle.metadata_json)
        deadline_value = (metadata.get("review") or {}).get("deadline")
        if not deadline_value:
            return False
        if isinstance(deadline_value, datetime):
            deadline = deadline_value
        else:
            deadline = datetime.fromisoformat(str(deadline_value))
        if deadline.tzinfo is None:
            return utcnow().replace(tzinfo=None) > deadline
        return utcnow() > deadline

    def _append_history(self, appeal: EvaluationAppeal, item: dict[str, Any]) -> None:
        metadata = metadata_load(appeal.metadata_json)
        history = metadata.setdefault("history", [])
        history.append(item)
        appeal.metadata_json = metadata_dump(metadata)

    def _audit(
        self,
        *,
        actor_user_id: str,
        action: str,
        resource_id: str,
        resource_type: str = "evaluation_appeal",
        before_snapshot: dict | None = None,
        after_snapshot: dict | None = None,
    ) -> None:
        actor = self.db.get(User, actor_user_id)
        create_audit_log(
            db=self.db,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            actor=actor,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
        )
