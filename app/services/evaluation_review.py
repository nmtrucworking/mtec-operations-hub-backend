from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.audit import create_audit_log
from app.core.evaluation_constants import (
    APPEAL_OPEN_STATUSES,
    CYCLE_STATUS_APPEAL_RESOLUTION,
    CYCLE_STATUS_DATA_COLLECTION,
    CYCLE_STATUS_DRAFT,
    CYCLE_STATUS_MEMBER_REVIEW,
    CYCLE_STATUS_READY_FOR_APPROVAL,
    CYCLE_STATUS_SCORING,
    MEMBER_EVALUATION_STATUS_APPEALED,
    MEMBER_EVALUATION_STATUS_COMPUTED,
    MEMBER_EVALUATION_STATUS_DRAFT,
    MEMBER_EVALUATION_STATUS_UNDER_REVIEW,
)
from app.models import EvaluationAppeal, EvaluationCycle, MemberEvaluation, User
from app.services.evaluation_errors import (
    EvaluationInvalidStatusTransitionError,
    EvaluationNotFoundError,
)
from app.services.evaluation_notification import EvaluationNotificationService
from app.services.evaluation_workflow_utils import (
    add_business_days,
    ensure_cycle_is_mutable,
    metadata_dump,
    metadata_load,
    utcnow,
)

OPEN_REVIEW_ALLOWED_STATUSES = {
    CYCLE_STATUS_DRAFT,
    CYCLE_STATUS_DATA_COLLECTION,
    CYCLE_STATUS_SCORING,
    CYCLE_STATUS_MEMBER_REVIEW,
}


class EvaluationReviewService:
    def __init__(self, db: Session):
        self.db = db
        self.notifications = EvaluationNotificationService()

    def open_member_review(
        self,
        cycle_id: str,
        *,
        actor_user_id: str,
        review_deadline: datetime | None = None,
        note: str | None = None,
    ) -> dict:
        cycle = self._get_cycle(cycle_id)
        ensure_cycle_is_mutable(cycle)
        if cycle.status not in OPEN_REVIEW_ALLOWED_STATUSES:
            raise EvaluationInvalidStatusTransitionError(
                f"Cannot open review from status {cycle.status}"
            )

        now = utcnow()
        deadline = review_deadline or add_business_days(now, 2)
        cycle.status = CYCLE_STATUS_MEMBER_REVIEW
        metadata = metadata_load(cycle.metadata_json)
        metadata["review"] = {
            "openedAt": now,
            "openedByUserId": actor_user_id,
            "deadline": deadline,
            "closedAt": None,
            "closedByUserId": None,
            "note": note,
        }
        cycle.metadata_json = metadata_dump(metadata)

        updated_members = self.db.execute(
            update(MemberEvaluation)
            .where(
                MemberEvaluation.cycle_id == cycle_id,
                MemberEvaluation.status.in_(
                    [
                        MEMBER_EVALUATION_STATUS_DRAFT,
                        MEMBER_EVALUATION_STATUS_COMPUTED,
                    ]
                ),
            )
            .values(status=MEMBER_EVALUATION_STATUS_UNDER_REVIEW)
        ).rowcount

        self._audit(
            actor_user_id=actor_user_id,
            action="OPEN_MEMBER_REVIEW",
            cycle_id=cycle_id,
            after_snapshot={
                "status": cycle.status,
                "reviewDeadline": deadline,
                "updatedMembers": updated_members,
            },
        )
        self.notifications.notify(
            "evaluation.review.opened",
            {"cycleId": cycle_id, "reviewDeadline": deadline},
        )
        self.db.flush()
        return {
            "cycle": cycle,
            "reviewDeadline": deadline,
            "updatedMembers": updated_members or 0,
        }

    def close_member_review(self, cycle_id: str, *, actor_user_id: str) -> dict:
        cycle = self._get_cycle(cycle_id)
        ensure_cycle_is_mutable(cycle)
        if cycle.status != CYCLE_STATUS_MEMBER_REVIEW:
            raise EvaluationInvalidStatusTransitionError(
                f"Cannot close review from status {cycle.status}"
            )

        open_appeals = self._count_open_appeals(cycle_id)
        next_status = (
            CYCLE_STATUS_APPEAL_RESOLUTION
            if open_appeals
            else CYCLE_STATUS_READY_FOR_APPROVAL
        )
        cycle.status = next_status
        metadata = metadata_load(cycle.metadata_json)
        review_metadata = metadata.get("review", {})
        review_metadata["closedAt"] = utcnow()
        review_metadata["closedByUserId"] = actor_user_id
        metadata["review"] = review_metadata
        cycle.metadata_json = metadata_dump(metadata)

        self.db.execute(
            update(MemberEvaluation)
            .where(
                MemberEvaluation.cycle_id == cycle_id,
                MemberEvaluation.status == MEMBER_EVALUATION_STATUS_UNDER_REVIEW,
            )
            .values(status=MEMBER_EVALUATION_STATUS_COMPUTED)
        )
        if open_appeals:
            appealed_member_ids = select(EvaluationAppeal.member_id).where(
                EvaluationAppeal.cycle_id == cycle_id,
                EvaluationAppeal.status.in_(APPEAL_OPEN_STATUSES),
            )
            self.db.execute(
                update(MemberEvaluation)
                .where(
                    MemberEvaluation.cycle_id == cycle_id,
                    MemberEvaluation.member_id.in_(appealed_member_ids),
                )
                .values(status=MEMBER_EVALUATION_STATUS_APPEALED)
            )

        self._audit(
            actor_user_id=actor_user_id,
            action="CLOSE_MEMBER_REVIEW",
            cycle_id=cycle_id,
            after_snapshot={"status": cycle.status, "openAppeals": open_appeals},
        )
        self.notifications.notify(
            "evaluation.review.closed",
            {"cycleId": cycle_id, "nextStatus": next_status},
        )
        self.db.flush()
        return {
            "cycle": cycle,
            "openAppeals": open_appeals,
            "nextStatus": next_status,
        }

    def get_review_summary(self, cycle_id: str) -> dict:
        cycle = self._get_cycle(cycle_id)
        metadata = metadata_load(cycle.metadata_json)
        appeal_status_counts = self._status_counts(
            EvaluationAppeal.status,
            EvaluationAppeal.cycle_id == cycle_id,
        )
        member_status_counts = self._status_counts(
            MemberEvaluation.status,
            MemberEvaluation.cycle_id == cycle_id,
        )
        open_appeals = sum(
            appeal_status_counts.get(status, 0) for status in APPEAL_OPEN_STATUSES
        )
        return {
            "cycleId": cycle_id,
            "cycleStatus": cycle.status,
            "review": metadata.get("review"),
            "memberStatusCounts": member_status_counts,
            "appealStatusCounts": appeal_status_counts,
            "openAppeals": open_appeals,
            "canCloseReview": cycle.status == CYCLE_STATUS_MEMBER_REVIEW,
            "canMarkReady": open_appeals == 0,
        }

    def _get_cycle(self, cycle_id: str) -> EvaluationCycle:
        cycle = self.db.get(EvaluationCycle, cycle_id)
        if not cycle:
            raise EvaluationNotFoundError(f"Evaluation cycle not found: {cycle_id}")
        return cycle

    def _count_open_appeals(self, cycle_id: str) -> int:
        return (
            self.db.scalar(
                select(func.count())
                .select_from(EvaluationAppeal)
                .where(
                    EvaluationAppeal.cycle_id == cycle_id,
                    EvaluationAppeal.status.in_(APPEAL_OPEN_STATUSES),
                )
            )
            or 0
        )

    def _status_counts(self, status_column, *conditions) -> dict[str, int]:
        rows = self.db.execute(
            select(status_column, func.count()).where(*conditions).group_by(status_column)
        ).all()
        return {status_value: count for status_value, count in rows}

    def _audit(
        self,
        *,
        actor_user_id: str,
        action: str,
        cycle_id: str,
        after_snapshot: dict,
    ) -> None:
        actor = self.db.get(User, actor_user_id)
        create_audit_log(
            db=self.db,
            action=action,
            resource_type="evaluation_cycle",
            resource_id=cycle_id,
            actor=actor,
            after_snapshot=after_snapshot,
        )
