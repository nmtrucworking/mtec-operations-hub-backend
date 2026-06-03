from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

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
)
from app.services.evaluation_sync import EvaluationSyncService


def _cycle(test_db: Session) -> EvaluationCycle:
    cycle = EvaluationCycle(
        code="2026-05-SYNC",
        name="Sync cycle",
        type="MONTHLY",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
    )
    test_db.add(cycle)
    test_db.flush()
    return cycle


def _member(test_db: Session, *, mssv: str = "SYNC001") -> Member:
    member = Member(mssv=mssv, name="Sync Tester")
    test_db.add(member)
    test_db.flush()
    return member


def _criterion(test_db: Session, *, code: str, component: str) -> EvaluationCriterion:
    criterion = EvaluationCriterion(
        code=code,
        name=code,
        component=component,
        unit_scope="ALL",
        max_score=10.0,
        score_method="MANUAL",
        requires_evidence=False,
    )
    test_db.add(criterion)
    test_db.flush()
    return criterion


def _meeting(test_db: Session) -> Meeting:
    meeting = Meeting(
        title="Monthly meeting",
        date=datetime(2026, 5, 10, tzinfo=UTC),
        meeting_type="Monthly",
    )
    test_db.add(meeting)
    test_db.flush()
    return meeting


def test_attendance_sync_is_idempotent(test_db: Session):
    cycle = _cycle(test_db)
    member = _member(test_db)
    _criterion(test_db, code="I.2", component="I")
    meeting = _meeting(test_db)
    test_db.add(
        Attendance(meeting_id=meeting.id, member_id=member.id, status="Absent")
    )
    test_db.flush()
    service = EvaluationSyncService(test_db)

    first = service.sync_attendance_to_score_events(cycle.id, meeting.id)
    second = service.sync_attendance_to_score_events(cycle.id, meeting.id)
    count = test_db.scalar(select(func.count()).select_from(EvaluationScoreEvent))

    assert first["createdCount"] == 1
    assert second["createdCount"] == 0
    assert second["skippedCount"] == 1
    assert count == 1


def test_absent_attendance_creates_penalty_event(test_db: Session):
    cycle = _cycle(test_db)
    member = _member(test_db)
    _criterion(test_db, code="I.2", component="I")
    meeting = _meeting(test_db)
    test_db.add(
        Attendance(meeting_id=meeting.id, member_id=member.id, status="Absent")
    )
    test_db.flush()

    EvaluationSyncService(test_db).sync_attendance_to_score_events(cycle.id, meeting.id)
    event = test_db.scalar(select(EvaluationScoreEvent))

    assert event is not None
    assert event.event_type == "PENALTY"
    assert event.source_type == "ATTENDANCE"
    assert event.source_id == meeting.id
    assert event.score_delta < 0


def test_excused_absence_does_not_create_unexcused_penalty(test_db: Session):
    cycle = _cycle(test_db)
    member = _member(test_db)
    _criterion(test_db, code="I.2", component="I")
    meeting = _meeting(test_db)
    test_db.add(
        Attendance(meeting_id=meeting.id, member_id=member.id, status="Excused")
    )
    test_db.flush()

    result = EvaluationSyncService(test_db).sync_attendance_to_score_events(
        cycle.id, meeting.id
    )
    count = test_db.scalar(select(func.count()).select_from(EvaluationScoreEvent))

    assert result["createdCount"] == 0
    assert count == 0


def test_attendance_sync_creates_rate_event_and_unexcused_blocker(test_db: Session):
    cycle = _cycle(test_db)
    member = _member(test_db)
    _criterion(test_db, code="I.1", component="I")
    _criterion(test_db, code="I.2", component="I")
    first_meeting = _meeting(test_db)
    second_meeting = _meeting(test_db)
    test_db.add_all(
        [
            Attendance(
                meeting_id=first_meeting.id,
                member_id=member.id,
                status="Present",
            ),
            Attendance(
                meeting_id=second_meeting.id,
                member_id=member.id,
                status="Absent",
            ),
        ]
    )
    test_db.flush()

    EvaluationSyncService(test_db).sync_attendance_to_score_events(
        cycle.id, second_meeting.id
    )

    rate_event = test_db.scalar(
        select(EvaluationScoreEvent).where(
            EvaluationScoreEvent.criterion_code == "I.1"
        )
    )
    case = test_db.scalar(select(DisciplineCase))

    assert rate_event is not None
    assert rate_event.raw_value == 0.5
    assert rate_event.source_type == "ATTENDANCE_AGGREGATE"
    assert case is not None
    assert case.blocker_code == "UNEXCUSED_ABSENCE"


def test_competition_sync_creates_bonus_event_once(test_db: Session):
    cycle = _cycle(test_db)
    member = _member(test_db)
    _criterion(test_db, code="III-A.5", component="III_A")
    competition = Competition(
        title="Innovation challenge",
        date=date(2026, 5, 20),
        scale="Club",
        status="Completed",
    )
    test_db.add(competition)
    test_db.flush()
    test_db.add(
        CompetitionResult(
            competition_id=competition.id,
            member_id=member.id,
            achievement="Top 3",
            bonus_kpi=2.5,
        )
    )
    test_db.flush()
    service = EvaluationSyncService(test_db)

    first = service.sync_competition_to_score_events(cycle.id, competition.id)
    second = service.sync_competition_to_score_events(cycle.id, competition.id)
    event = test_db.scalar(select(EvaluationScoreEvent))
    count = test_db.scalar(select(func.count()).select_from(EvaluationScoreEvent))

    assert first["createdCount"] == 1
    assert second["createdCount"] == 0
    assert second["skippedCount"] == 1
    assert count == 1
    assert event.event_type == "BONUS"
    assert event.source_type == "COMPETITION"
    assert event.score_delta == 2.5


def test_sync_attendance_rejects_out_of_range_date(test_db: Session):
    cycle = _cycle(test_db)
    member = _member(test_db)
    _criterion(test_db, code="I.2", component="I")
    
    # Meeting is in June, outside of cycle (May)
    meeting = Meeting(
        title="June meeting",
        date=datetime(2026, 6, 10, tzinfo=UTC),
        meeting_type="Monthly",
    )
    test_db.add(meeting)
    test_db.flush()
    test_db.add(
        Attendance(meeting_id=meeting.id, member_id=member.id, status="Absent")
    )
    test_db.flush()
    
    from app.services.evaluation_errors import EvaluationValidationError
    import pytest
    
    service = EvaluationSyncService(test_db)
    with pytest.raises(EvaluationValidationError) as exc_info:
        service.sync_attendance_to_score_events(cycle.id, meeting.id)
    
    assert "outside of cycle range" in str(exc_info.value)


def test_sync_competition_rejects_out_of_range_date(test_db: Session):
    cycle = _cycle(test_db)
    member = _member(test_db)
    _criterion(test_db, code="III-A.5", component="III_A")
    
    # Competition is in June, outside of cycle (May)
    competition = Competition(
        title="Innovation challenge",
        date=date(2026, 6, 20),
        scale="Club",
        status="Completed",
    )
    test_db.add(competition)
    test_db.flush()
    test_db.add(
        CompetitionResult(
            competition_id=competition.id,
            member_id=member.id,
            achievement="Top 3",
            bonus_kpi=2.5,
        )
    )
    test_db.flush()
    
    from app.services.evaluation_errors import EvaluationValidationError
    import pytest
    
    service = EvaluationSyncService(test_db)
    with pytest.raises(EvaluationValidationError) as exc_info:
        service.sync_competition_to_score_events(cycle.id, competition.id)
        
    assert "outside of cycle range" in str(exc_info.value)
