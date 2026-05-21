from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.audit import create_audit_log
from app.core.evaluation_constants import (
    APPEAL_OPEN_STATUSES,
    CYCLE_STATUS_APPEAL_RESOLUTION,
    CYCLE_STATUS_APPROVED,
    CYCLE_STATUS_LOCKED,
    CYCLE_STATUS_MEMBER_REVIEW,
    CYCLE_STATUS_READY_FOR_APPROVAL,
    MEMBER_EVALUATION_STATUS_APPEAL_RESOLVED,
    MEMBER_EVALUATION_STATUS_APPEALED,
    MEMBER_EVALUATION_STATUS_APPROVED,
    MEMBER_EVALUATION_STATUS_DRAFT,
    MEMBER_EVALUATION_STATUS_LOCKED,
    MEMBER_EVALUATION_STATUS_UNDER_REVIEW,
)
from app.models import EvaluationAppeal, EvaluationCycle, MemberEvaluation, User
from app.services.evaluation_errors import (
    EvaluationCorrectionNotAllowedError,
    EvaluationCycleAlreadyApprovedError,
    EvaluationInvalidStatusTransitionError,
    EvaluationNotFoundError,
    EvaluationNotReadyForApprovalError,
    EvaluationOpenAppealsExistError,
)
from app.services.evaluation_notification import EvaluationNotificationService
from app.services.evaluation_workflow_utils import (
    metadata_dump,
    metadata_load,
    utcnow,
)

UNSTABLE_MEMBER_STATUSES = {
    MEMBER_EVALUATION_STATUS_DRAFT,
    MEMBER_EVALUATION_STATUS_UNDER_REVIEW,
    MEMBER_EVALUATION_STATUS_APPEALED,
}


class EvaluationApprovalService:
    def __init__(self, db: Session):
        self.db = db
        self.notifications = EvaluationNotificationService()

    def mark_ready_for_approval(self, cycle_id: str, *, actor_user_id: str) -> dict:
        cycle = self._get_cycle(cycle_id)
        if cycle.status == CYCLE_STATUS_LOCKED:
            raise EvaluationInvalidStatusTransitionError("Locked cycle cannot be marked ready")
        if cycle.status == CYCLE_STATUS_APPROVED:
            raise EvaluationCycleAlreadyApprovedError(f"Cycle already approved: {cycle_id}")

        self._ensure_ready_for_approval(cycle_id, allow_member_review=True)
        if cycle.status == CYCLE_STATUS_MEMBER_REVIEW:
            self.db.execute(
                update(MemberEvaluation)
                .where(
                    MemberEvaluation.cycle_id == cycle_id,
                    MemberEvaluation.status == MEMBER_EVALUATION_STATUS_UNDER_REVIEW,
                )
                .values(status=MEMBER_EVALUATION_STATUS_APPEAL_RESOLVED)
            )
        before_status = cycle.status
        cycle.status = CYCLE_STATUS_READY_FOR_APPROVAL
        self._audit(
            actor_user_id=actor_user_id,
            action="MARK_EVALUATION_READY_FOR_APPROVAL",
            resource_id=cycle_id,
            before_snapshot={"status": before_status},
            after_snapshot={"status": cycle.status},
        )
        self.notifications.notify(
            "evaluation.cycle.ready_for_approval",
            {"cycleId": cycle_id},
        )
        self.db.flush()
        return {"cycle": cycle, "details": self._readiness_details(cycle_id)}

    def approve_cycle(
        self,
        cycle_id: str,
        *,
        actor_user_id: str,
        approval_note: str | None = None,
        lock_after_approve: bool = False,
    ) -> dict:
        cycle = self._get_cycle(cycle_id)
        if cycle.status == CYCLE_STATUS_LOCKED:
            raise EvaluationInvalidStatusTransitionError("Locked cycle cannot be approved")
        if cycle.status == CYCLE_STATUS_APPROVED:
            raise EvaluationCycleAlreadyApprovedError(f"Cycle already approved: {cycle_id}")
        if cycle.status != CYCLE_STATUS_READY_FOR_APPROVAL:
            raise EvaluationInvalidStatusTransitionError(
                f"Cycle must be READY_FOR_APPROVAL before approval, got {cycle.status}"
            )

        self._ensure_ready_for_approval(cycle_id)
        cycle.status = CYCLE_STATUS_APPROVED
        cycle.approved_by_user_id = actor_user_id
        cycle.approved_at = utcnow()
        metadata = metadata_load(cycle.metadata_json)
        metadata["approval"] = {
            "approvedAt": cycle.approved_at,
            "approvedByUserId": actor_user_id,
            "note": approval_note,
        }
        cycle.metadata_json = metadata_dump(metadata)

        approved_count = self.db.execute(
            update(MemberEvaluation)
            .where(MemberEvaluation.cycle_id == cycle_id)
            .values(
                status=MEMBER_EVALUATION_STATUS_APPROVED,
                approved_by_user_id=actor_user_id,
                approved_at=cycle.approved_at,
            )
        ).rowcount
        self._audit(
            actor_user_id=actor_user_id,
            action="APPROVE_EVALUATION_CYCLE",
            resource_id=cycle_id,
            after_snapshot={
                "status": cycle.status,
                "approvedMembers": approved_count or 0,
                "lockAfterApprove": lock_after_approve,
            },
        )
        self.notifications.notify(
            "evaluation.cycle.approved",
            {"cycleId": cycle_id, "approvedMembers": approved_count or 0},
        )

        if lock_after_approve:
            self._lock_approved_cycle(cycle, actor_user_id=actor_user_id)
        self.db.flush()
        return {"cycle": cycle, "approvedMembers": approved_count or 0}

    def lock_cycle(self, cycle_id: str, *, actor_user_id: str) -> dict:
        cycle = self._get_cycle(cycle_id)
        if cycle.status == CYCLE_STATUS_LOCKED:
            return {"cycle": cycle, "lockedMembers": self._count_member_evaluations(cycle_id)}
        if cycle.status != CYCLE_STATUS_APPROVED:
            raise EvaluationInvalidStatusTransitionError(
                f"Cycle must be APPROVED before lock, got {cycle.status}"
            )
        locked_members = self._lock_approved_cycle(cycle, actor_user_id=actor_user_id)
        self.db.flush()
        return {"cycle": cycle, "lockedMembers": locked_members}

    def reopen_approved_cycle_for_correction(
        self,
        cycle_id: str,
        reason: str,
        *,
        actor_user_id: str,
    ) -> EvaluationCycle:
        cycle = self._get_cycle(cycle_id)
        if cycle.status == CYCLE_STATUS_LOCKED:
            raise EvaluationCorrectionNotAllowedError("Locked cycle cannot be reopened")
        if cycle.status != CYCLE_STATUS_APPROVED:
            raise EvaluationCorrectionNotAllowedError(
                f"Only APPROVED cycle can be reopened, got {cycle.status}"
            )

        before_status = cycle.status
        cycle.status = CYCLE_STATUS_APPEAL_RESOLUTION
        cycle.approved_by_user_id = None
        cycle.approved_at = None
        metadata = metadata_load(cycle.metadata_json)
        metadata["correction"] = {
            "reopenedAt": utcnow(),
            "reopenedByUserId": actor_user_id,
            "reason": reason,
        }
        cycle.metadata_json = metadata_dump(metadata)
        self.db.execute(
            update(MemberEvaluation)
            .where(
                MemberEvaluation.cycle_id == cycle_id,
                MemberEvaluation.status == MEMBER_EVALUATION_STATUS_APPROVED,
            )
            .values(
                status=MEMBER_EVALUATION_STATUS_APPEAL_RESOLVED,
                approved_by_user_id=None,
                approved_at=None,
            )
        )
        self._audit(
            actor_user_id=actor_user_id,
            action="REOPEN_EVALUATION_CORRECTION",
            resource_id=cycle_id,
            before_snapshot={"status": before_status},
            after_snapshot={"status": cycle.status, "reason": reason},
        )
        self.notifications.notify(
            "evaluation.cycle.reopened_for_correction",
            {"cycleId": cycle_id, "reason": reason},
        )
        self.db.flush()
        return cycle

    def _lock_approved_cycle(self, cycle: EvaluationCycle, *, actor_user_id: str) -> int:
        now = utcnow()
        cycle.status = CYCLE_STATUS_LOCKED
        cycle.locked_at = now
        locked_members = self.db.execute(
            update(MemberEvaluation)
            .where(MemberEvaluation.cycle_id == cycle.id)
            .values(status=MEMBER_EVALUATION_STATUS_LOCKED)
        ).rowcount
        self._audit(
            actor_user_id=actor_user_id,
            action="LOCK_EVALUATION_CYCLE",
            resource_id=cycle.id,
            after_snapshot={"status": cycle.status, "lockedMembers": locked_members or 0},
        )
        self.notifications.notify(
            "evaluation.cycle.locked",
            {"cycleId": cycle.id, "lockedMembers": locked_members or 0},
        )
        return locked_members or 0

    def _ensure_ready_for_approval(
        self,
        cycle_id: str,
        *,
        allow_member_review: bool = False,
    ) -> None:
        details = self._readiness_details(cycle_id)
        if details["openAppeals"]:
            raise EvaluationOpenAppealsExistError(
                "Evaluation cycle has open appeals",
                details=details,
            )
        unstable = details["unstableMemberEvaluations"]
        if allow_member_review:
            unstable -= details["memberStatusCounts"].get(
                MEMBER_EVALUATION_STATUS_UNDER_REVIEW, 0
            )
        if details["totalMemberEvaluations"] == 0 or unstable > 0:
            raise EvaluationNotReadyForApprovalError(
                "Evaluation cycle is not ready for approval",
                details={**details, "unstableMemberEvaluations": unstable},
            )

    def _readiness_details(self, cycle_id: str) -> dict:
        member_counts = {
            status_value: count
            for status_value, count in self.db.execute(
                select(MemberEvaluation.status, func.count())
                .where(MemberEvaluation.cycle_id == cycle_id)
                .group_by(MemberEvaluation.status)
            ).all()
        }
        open_appeals = (
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
        total = sum(member_counts.values())
        unstable = sum(member_counts.get(status, 0) for status in UNSTABLE_MEMBER_STATUSES)
        return {
            "totalMemberEvaluations": total,
            "openAppeals": open_appeals,
            "unstableMemberEvaluations": unstable,
            "memberStatusCounts": member_counts,
        }

    def _count_member_evaluations(self, cycle_id: str) -> int:
        return (
            self.db.scalar(
                select(func.count())
                .select_from(MemberEvaluation)
                .where(MemberEvaluation.cycle_id == cycle_id)
            )
            or 0
        )

    def _get_cycle(self, cycle_id: str) -> EvaluationCycle:
        cycle = self.db.get(EvaluationCycle, cycle_id)
        if not cycle:
            raise EvaluationNotFoundError(f"Evaluation cycle not found: {cycle_id}")
        return cycle

    def _audit(
        self,
        *,
        actor_user_id: str,
        action: str,
        resource_id: str,
        before_snapshot: dict | None = None,
        after_snapshot: dict | None = None,
    ) -> None:
        actor = self.db.get(User, actor_user_id)
        create_audit_log(
            db=self.db,
            action=action,
            resource_type="evaluation_cycle",
            resource_id=resource_id,
            actor=actor,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
        )
