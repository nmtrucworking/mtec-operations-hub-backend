from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import create_audit_log
from app.core.evaluation_constants import (
    CYCLE_MUTABLE_STATUSES,
    DEFAULT_ATTENDANCE_PENALTY_CRITERION_CODE,
    DEFAULT_COMPETITION_BONUS_CRITERION_CODE,
    EVENT_TYPE_BONUS,
    EVENT_TYPE_PENALTY,
    SOURCE_TYPE_ATTENDANCE,
    SOURCE_TYPE_COMPETITION,
)
from app.models import (
    Attendance,
    Competition,
    CompetitionResult,
    EvaluationCriterion,
    EvaluationCycle,
    EvaluationScoreEvent,
    Meeting,
    User,
)
from app.services.evaluation_errors import (
    EvaluationCycleLockedError,
    EvaluationMissingCriteriaError,
    EvaluationNotFoundError,
)


class EvaluationSyncService:
    def __init__(self, db: Session):
        self.db = db

    def sync_attendance_to_score_events(
        self,
        cycle_id: str,
        meeting_id: str,
        *,
        actor_user_id: str | None = None,
    ) -> dict:
        self._ensure_cycle_writable(cycle_id)
        meeting = self.db.get(Meeting, meeting_id)
        if not meeting:
            raise EvaluationNotFoundError(f"Meeting not found: {meeting_id}")

        criterion = self._get_active_criterion(DEFAULT_ATTENDANCE_PENALTY_CRITERION_CODE)
        attendances = self.db.scalars(
            select(Attendance).where(Attendance.meeting_id == meeting_id)
        ).all()

        created = 0
        skipped = 0
        for attendance in attendances:
            if attendance.status != "Absent":
                continue
            if self._score_event_exists(
                cycle_id=cycle_id,
                member_id=attendance.member_id,
                criterion_code=criterion.code,
                source_type=SOURCE_TYPE_ATTENDANCE,
                source_id=meeting_id,
                event_type=EVENT_TYPE_PENALTY,
            ):
                skipped += 1
                continue

            self.db.add(
                EvaluationScoreEvent(
                    cycle_id=cycle_id,
                    member_id=attendance.member_id,
                    criterion_id=criterion.id,
                    criterion_code=criterion.code,
                    component=criterion.component,
                    unit_code=criterion.unit_code,
                    event_type=EVENT_TYPE_PENALTY,
                    source_type=SOURCE_TYPE_ATTENDANCE,
                    source_id=meeting_id,
                    raw_value=1.0,
                    score_delta=-1.0,
                    max_score_snapshot=criterion.max_score,
                    recorded_by_user_id=actor_user_id,
                    note=f"Unexcused absence in meeting {meeting_id}",
                )
            )
            created += 1

        self._audit(
            actor_user_id=actor_user_id,
            action="SYNC_ATTENDANCE_SCORE_EVENTS",
            resource_id=meeting_id,
            created=created,
            skipped=skipped,
        )
        self.db.flush()

        return {
            "cycleId": cycle_id,
            "meetingId": meeting_id,
            "createdCount": created,
            "skippedCount": skipped,
        }

    def sync_competition_to_score_events(
        self,
        cycle_id: str,
        competition_id: str,
        *,
        actor_user_id: str | None = None,
    ) -> dict:
        self._ensure_cycle_writable(cycle_id)
        competition = self.db.get(Competition, competition_id)
        if not competition:
            raise EvaluationNotFoundError(f"Competition not found: {competition_id}")

        criterion = self._get_active_criterion(DEFAULT_COMPETITION_BONUS_CRITERION_CODE)
        results = self.db.scalars(
            select(CompetitionResult).where(
                CompetitionResult.competition_id == competition_id,
                CompetitionResult.bonus_kpi > 0,
            )
        ).all()

        created = 0
        skipped = 0
        for result in results:
            source_id = result.id
            if self._score_event_exists(
                cycle_id=cycle_id,
                member_id=result.member_id,
                criterion_code=criterion.code,
                source_type=SOURCE_TYPE_COMPETITION,
                source_id=source_id,
                event_type=EVENT_TYPE_BONUS,
            ):
                skipped += 1
                continue

            self.db.add(
                EvaluationScoreEvent(
                    cycle_id=cycle_id,
                    member_id=result.member_id,
                    criterion_id=criterion.id,
                    criterion_code=criterion.code,
                    component=criterion.component,
                    unit_code=criterion.unit_code,
                    event_type=EVENT_TYPE_BONUS,
                    source_type=SOURCE_TYPE_COMPETITION,
                    source_id=source_id,
                    raw_value=result.bonus_kpi,
                    score_delta=result.bonus_kpi,
                    max_score_snapshot=criterion.max_score,
                    recorded_by_user_id=actor_user_id,
                    note=f"Competition bonus from {competition_id}: {result.achievement}",
                )
            )
            created += 1

        self._audit(
            actor_user_id=actor_user_id,
            action="SYNC_COMPETITION_SCORE_EVENTS",
            resource_id=competition_id,
            created=created,
            skipped=skipped,
        )
        self.db.flush()

        return {
            "cycleId": cycle_id,
            "competitionId": competition_id,
            "createdCount": created,
            "skippedCount": skipped,
        }

    def _ensure_cycle_writable(self, cycle_id: str) -> None:
        cycle = self.db.get(EvaluationCycle, cycle_id)
        if not cycle:
            raise EvaluationNotFoundError(f"Evaluation cycle not found: {cycle_id}")
        if cycle.status not in CYCLE_MUTABLE_STATUSES:
            raise EvaluationCycleLockedError(
                f"Evaluation cycle is not writable in status {cycle.status}: {cycle_id}"
            )

    def _get_active_criterion(self, criterion_code: str) -> EvaluationCriterion:
        criterion = self.db.scalar(
            select(EvaluationCriterion).where(
                EvaluationCriterion.code == criterion_code,
                EvaluationCriterion.is_active.is_(True),
            )
        )
        if not criterion:
            raise EvaluationMissingCriteriaError(
                f"Active criterion not found: {criterion_code}"
            )
        return criterion

    def _score_event_exists(
        self,
        *,
        cycle_id: str,
        member_id: str,
        criterion_code: str,
        source_type: str,
        source_id: str,
        event_type: str,
    ) -> bool:
        return (
            self.db.scalar(
                select(EvaluationScoreEvent.id).where(
                    EvaluationScoreEvent.cycle_id == cycle_id,
                    EvaluationScoreEvent.member_id == member_id,
                    EvaluationScoreEvent.criterion_code == criterion_code,
                    EvaluationScoreEvent.source_type == source_type,
                    EvaluationScoreEvent.source_id == source_id,
                    EvaluationScoreEvent.event_type == event_type,
                    EvaluationScoreEvent.is_void.is_(False),
                )
            )
            is not None
        )

    def _audit(
        self,
        *,
        actor_user_id: str | None,
        action: str,
        resource_id: str,
        created: int,
        skipped: int,
    ) -> None:
        actor = self.db.get(User, actor_user_id) if actor_user_id else None
        create_audit_log(
            db=self.db,
            action=action,
            resource_type="evaluation_sync",
            resource_id=resource_id,
            actor=actor,
            after_snapshot={"created": created, "skipped": skipped},
        )
