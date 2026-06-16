from datetime import datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import create_audit_log
from app.core.departments import extract_member_department_codes
from app.core.evaluation_constants import (
    BLOCKER_UNEXCUSED_ABSENCE,
    CYCLE_MUTABLE_STATUSES,
    DEFAULT_ATTENDANCE_RATE_CRITERION_CODE,
    DEFAULT_ATTENDANCE_PENALTY_CRITERION_CODE,
    DEFAULT_COMPETITION_BONUS_CRITERION_CODE,
    EVENT_TYPE_BASE,
    EVENT_TYPE_BONUS,
    EVENT_TYPE_PENALTY,
    SOURCE_TYPE_ATTENDANCE_AGGREGATE,
    SOURCE_TYPE_ATTENDANCE,
    SOURCE_TYPE_COMPETITION,
)
from app.models import (
    Attendance,
    Competition,
    CompetitionResult,
    DisciplineCase,
    EvaluationCriterion,
    EvaluationCycle,
    EvaluationScoreEvent,
    Meeting,
    Member,
    MemberCycleRole,
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

        cycle = self.db.get(EvaluationCycle, cycle_id)
        if cycle:
            meeting_date_date = meeting.date.date()
            if not (cycle.start_date <= meeting_date_date <= cycle.end_date):
                from app.services.evaluation_errors import EvaluationValidationError
                raise EvaluationValidationError(
                    f"Meeting date ({meeting_date_date}) is outside of cycle range ({cycle.start_date} to {cycle.end_date})"
                )

        criterion = self._get_active_criterion(DEFAULT_ATTENDANCE_PENALTY_CRITERION_CODE)
        attendance_rate_criterion = self._get_optional_active_criterion(
            DEFAULT_ATTENDANCE_RATE_CRITERION_CODE
        )
        attendances = self.db.scalars(
            select(Attendance).where(Attendance.meeting_id == meeting_id)
        ).all()

        created = 0
        skipped = 0
        touched_member_ids: set[str] = set()
        for attendance in attendances:
            touched_member_ids.add(attendance.member_id)
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
            self._ensure_unexcused_absence_case(
                cycle_id=cycle_id,
                member_id=attendance.member_id,
                meeting_id=meeting_id,
                actor_user_id=actor_user_id,
            )

        if cycle and attendance_rate_criterion:
            for member_id in touched_member_ids:
                self._upsert_attendance_rate_event(
                    cycle=cycle,
                    member_id=member_id,
                    criterion=attendance_rate_criterion,
                    actor_user_id=actor_user_id,
                )

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

    def init_cycle_baseline(
        self,
        cycle_id: str,
        *,
        actor_user_id: str | None = None,
    ) -> dict:
        self._ensure_cycle_writable(cycle_id)
        cycle = self.db.get(EvaluationCycle, cycle_id)
        if not cycle:
            raise EvaluationNotFoundError(f"Evaluation cycle not found: {cycle_id}")

        active_members = self.db.scalars(
            select(Member).where(Member.status == "Active")
        ).all()

        created_roles = 0
        created_events = 0

        for member in active_members:
            department_codes = extract_member_department_codes(member)
            if not department_codes:
                continue

            existing_role = self.db.scalar(
                select(MemberCycleRole).where(
                    MemberCycleRole.cycle_id == cycle_id,
                    MemberCycleRole.member_id == member.id,
                )
            )
            if not existing_role:
                for index, code in enumerate(department_codes):
                    role = MemberCycleRole(
                        cycle_id=cycle_id,
                        member_id=member.id,
                        unit_code=code,
                        role_title=member.role_title or "Thành viên",
                        participation_weight=1.0 / len(department_codes),
                        is_primary=index == 0,
                        assigned_by_user_id=actor_user_id,
                    )
                    self.db.add(role)
                    created_roles += 1

            criterion_ii2 = self._get_optional_active_criterion("II.2")
            if criterion_ii2:
                if not self._score_event_exists(
                    cycle_id=cycle_id,
                    member_id=member.id,
                    criterion_code=criterion_ii2.code,
                    source_type="BASELINE_INIT",
                    source_id="baseline",
                    event_type=EVENT_TYPE_BASE,
                ):
                    self.db.add(
                        EvaluationScoreEvent(
                            cycle_id=cycle_id,
                            member_id=member.id,
                            criterion_id=criterion_ii2.id,
                            criterion_code=criterion_ii2.code,
                            component=criterion_ii2.component,
                            unit_code=criterion_ii2.unit_code,
                            event_type=EVENT_TYPE_BASE,
                            source_type="BASELINE_INIT",
                            source_id="baseline",
                            raw_value=criterion_ii2.max_score,
                            score_delta=criterion_ii2.max_score,
                            max_score_snapshot=criterion_ii2.max_score,
                            recorded_by_user_id=actor_user_id,
                            note="Điểm nền tự động thiết lập",
                        )
                    )
                    created_events += 1

        self._audit(
            actor_user_id=actor_user_id,
            action="INIT_CYCLE_BASELINE",
            resource_id=cycle_id,
            created=created_roles + created_events,
            skipped=0,
        )
        self.db.flush()

        return {
            "cycleId": cycle_id,
            "createdRoles": created_roles,
            "createdEvents": created_events,
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

        cycle = self.db.get(EvaluationCycle, cycle_id)
        if cycle:
            if not (cycle.start_date <= competition.date <= cycle.end_date):
                from app.services.evaluation_errors import EvaluationValidationError
                raise EvaluationValidationError(
                    f"Competition date ({competition.date}) is outside of cycle range ({cycle.start_date} to {cycle.end_date})"
                )

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

    def _get_optional_active_criterion(
        self, criterion_code: str
    ) -> EvaluationCriterion | None:
        return self.db.scalar(
            select(EvaluationCriterion).where(
                EvaluationCriterion.code == criterion_code,
                EvaluationCriterion.is_active.is_(True),
            )
        )

    def _upsert_attendance_rate_event(
        self,
        *,
        cycle: EvaluationCycle,
        member_id: str,
        criterion: EvaluationCriterion,
        actor_user_id: str | None,
    ) -> None:
        start_at = datetime.combine(cycle.start_date, time.min)
        end_at = datetime.combine(cycle.end_date, time.max)
        attendances = self.db.scalars(
            select(Attendance)
            .join(Meeting, Meeting.id == Attendance.meeting_id)
            .where(
                Attendance.member_id == member_id,
                Meeting.date >= start_at,
                Meeting.date <= end_at,
                Attendance.status.in_(("Present", "Absent", "Excused")),
            )
        ).all()
        required_count = len(attendances)
        if required_count == 0:
            return

        present_count = sum(1 for item in attendances if item.status == "Present")
        attendance_rate = present_count / required_count
        score_delta = attendance_rate * criterion.max_score
        source_id = f"{cycle.id[:12]}:{member_id[:12]}:attendance_rate"

        existing = self.db.scalar(
            select(EvaluationScoreEvent).where(
                EvaluationScoreEvent.cycle_id == cycle.id,
                EvaluationScoreEvent.member_id == member_id,
                EvaluationScoreEvent.criterion_code == criterion.code,
                EvaluationScoreEvent.source_type == SOURCE_TYPE_ATTENDANCE_AGGREGATE,
                EvaluationScoreEvent.source_id == source_id,
                EvaluationScoreEvent.event_type == EVENT_TYPE_BASE,
                EvaluationScoreEvent.is_void.is_(False),
            )
        )
        note = (
            f"Attendance rate {attendance_rate:.2%} "
            f"({present_count}/{required_count} recorded meetings)"
        )
        if existing:
            existing.raw_value = attendance_rate
            existing.score_delta = score_delta
            existing.max_score_snapshot = criterion.max_score
            existing.note = note
            return

        self.db.add(
            EvaluationScoreEvent(
                cycle_id=cycle.id,
                member_id=member_id,
                criterion_id=criterion.id,
                criterion_code=criterion.code,
                component=criterion.component,
                unit_code=criterion.unit_code,
                event_type=EVENT_TYPE_BASE,
                source_type=SOURCE_TYPE_ATTENDANCE_AGGREGATE,
                source_id=source_id,
                raw_value=attendance_rate,
                score_delta=score_delta,
                max_score_snapshot=criterion.max_score,
                recorded_by_user_id=actor_user_id,
                note=note,
            )
        )

    def _ensure_unexcused_absence_case(
        self,
        *,
        cycle_id: str,
        member_id: str,
        meeting_id: str,
        actor_user_id: str | None,
    ) -> None:
        existing = self.db.scalar(
            select(DisciplineCase).where(
                DisciplineCase.cycle_id == cycle_id,
                DisciplineCase.member_id == member_id,
                DisciplineCase.source_type == SOURCE_TYPE_ATTENDANCE,
                DisciplineCase.source_id == meeting_id,
                DisciplineCase.status != "CANCELLED",
            )
        )
        if existing:
            return

        self.db.add(
            DisciplineCase(
                cycle_id=cycle_id,
                member_id=member_id,
                case_code=f"ATT-{meeting_id[:12]}-{member_id[:12]}",
                case_type="UNEXCUSED_ABSENCE",
                severity="MEDIUM",
                status="OPEN",
                title="Unexcused absence",
                description=f"Unexcused absence in meeting {meeting_id}",
                blocker_code=BLOCKER_UNEXCUSED_ABSENCE,
                source_type=SOURCE_TYPE_ATTENDANCE,
                source_id=meeting_id,
                created_by_user_id=actor_user_id,
            )
        )

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
