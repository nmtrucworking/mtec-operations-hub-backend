from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import (
    Attendance,
    Competition,
    CompetitionResult,
    DisciplineCase,
    DisciplineRecord,
    EvaluationCriterion,
    EvaluationCycle,
    EvaluationEvidence,
    EvaluationScoreEvent,
    Meeting,
    Member,
    MemberEvaluation,
    User,
)
from app.services.evaluation_legacy_migration import (
    EvaluationLegacyMigrationService,
    map_discipline_level,
)


def _auth_header(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def _user(test_db: Session, username: str, role: str = "bcn") -> User:
    user = User(
        id=f"user-{username}",
        username=username,
        password_hash="hashed",
        full_name=username.title(),
        role=role,
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    return user


def _member(test_db: Session, mssv: str = "LEGACY001") -> Member:
    member = Member(mssv=mssv, name=f"Member {mssv}", ban="BCNg")
    test_db.add(member)
    test_db.commit()
    return member


def _cycle(test_db: Session, code: str = "P5-CYCLE") -> EvaluationCycle:
    cycle = EvaluationCycle(
        code=code,
        name=code,
        type="MONTHLY",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
        status="SCORING",
    )
    test_db.add(cycle)
    test_db.commit()
    return cycle


def _criterion(test_db: Session, code: str, *, component: str = "I", max_score: float = 10):
    criterion = EvaluationCriterion(
        code=code,
        name=code,
        component=component,
        unit_scope="ALL",
        max_score=max_score,
        score_method="MANUAL",
        requires_evidence=False,
    )
    test_db.add(criterion)
    test_db.commit()
    return criterion


def _seed_phase5_criteria(test_db: Session):
    _criterion(test_db, "I.2", component="I", max_score=30)
    _criterion(test_db, "III-A.5", component="III_A", max_score=3)


def _discipline_record(
    test_db: Session,
    member: Member | None,
    *,
    mssv: str | None = None,
    absents: int = 0,
    kpi: float = 0,
    discipline_level: str = "Khong",
) -> DisciplineRecord:
    record = DisciplineRecord(
        member_id=member.id if member else None,
        mssv=mssv or (member.mssv if member else "UNKNOWN"),
        name=member.name if member else "Unknown",
        committee=member.ban if member else None,
        absents=absents,
        kpi=kpi,
        discipline_level=discipline_level,
    )
    test_db.add(record)
    test_db.commit()
    return record


def _meeting_with_attendance(
    test_db: Session,
    member: Member,
    *,
    status: str = "Absent",
) -> Attendance:
    meeting = Meeting(
        title="Legacy meeting",
        date=datetime(2026, 5, 10, tzinfo=UTC),
        meeting_type="Monthly",
        status="Completed",
    )
    test_db.add(meeting)
    test_db.flush()
    attendance = Attendance(meeting_id=meeting.id, member_id=member.id, status=status)
    test_db.add(attendance)
    test_db.commit()
    return attendance


def _competition_result(
    test_db: Session,
    member: Member,
    *,
    bonus_kpi: float = 2.5,
) -> CompetitionResult:
    competition = Competition(
        title="Legacy competition",
        date=date(2026, 5, 15),
        scale="Club",
        status="Completed",
    )
    test_db.add(competition)
    test_db.flush()
    result = CompetitionResult(
        competition_id=competition.id,
        member_id=member.id,
        achievement="Top 5",
        bonus_kpi=bonus_kpi,
    )
    test_db.add(result)
    test_db.commit()
    return result


def test_inventory_counts_discipline_records(test_db: Session):
    member = _member(test_db)
    _discipline_record(test_db, member, absents=2, kpi=95, discipline_level="Nhac nho")
    _discipline_record(test_db, None, mssv="MISSING", discipline_level="Khong")

    inventory = EvaluationLegacyMigrationService(test_db).build_inventory()

    assert inventory["disciplineRecords"]["total"] == 2
    assert inventory["disciplineRecords"]["withMemberId"] == 1
    assert inventory["disciplineRecords"]["withoutMemberId"] == 1
    assert inventory["disciplineRecords"]["absents"]["max"] == 2


def test_inventory_counts_attendance_statuses(test_db: Session):
    member = _member(test_db)
    _meeting_with_attendance(test_db, member, status="Absent")
    _meeting_with_attendance(test_db, member, status="Excused")

    inventory = EvaluationLegacyMigrationService(test_db).build_inventory()

    assert inventory["attendances"]["total"] == 2
    assert inventory["attendances"]["statusDistribution"]["Absent"] == 1
    assert inventory["attendances"]["statusDistribution"]["Excused"] == 1


def test_inventory_detects_unmatched_members(test_db: Session):
    _discipline_record(test_db, None, mssv="NO_MATCH")

    inventory = EvaluationLegacyMigrationService(test_db).build_inventory()

    assert inventory["disciplineRecords"]["unmatchedRecords"][0]["mssv"] == "NO_MATCH"


def test_map_discipline_warning_to_discipline_case(test_db: Session):
    member = _member(test_db)
    cycle = _cycle(test_db)
    _seed_phase5_criteria(test_db)
    _discipline_record(test_db, member, discipline_level="Canh cao Lan 1")

    summary = EvaluationLegacyMigrationService(test_db).migrate(
        cycle.id,
        mode="sandbox",
        migration_batch_id="batch-warning",
    )
    test_db.commit()
    case = test_db.scalar(select(DisciplineCase))

    assert summary["createdDisciplineCases"] == 1
    assert case.case_type == "WARNING"
    assert case.blocker_code == "INTERNAL_WARNING"


def test_map_no_discipline_level_skips_case(test_db: Session):
    member = _member(test_db)
    cycle = _cycle(test_db)
    _seed_phase5_criteria(test_db)
    _discipline_record(test_db, member, discipline_level="Khong")

    summary = EvaluationLegacyMigrationService(test_db).migrate(
        cycle.id,
        mode="sandbox",
        migration_batch_id="batch-no-level",
    )

    assert summary["createdDisciplineCases"] == 0


def test_map_absents_to_legacy_score_event(test_db: Session):
    member = _member(test_db)
    cycle = _cycle(test_db)
    _seed_phase5_criteria(test_db)
    _discipline_record(test_db, member, absents=2)

    summary = EvaluationLegacyMigrationService(test_db).migrate(
        cycle.id,
        mode="sandbox",
        migration_batch_id="batch-absents",
    )
    test_db.commit()
    event = test_db.scalar(
        select(EvaluationScoreEvent).where(
            EvaluationScoreEvent.source_type == "LEGACY_DISCIPLINE_RECORD"
        )
    )

    assert summary["createdScoreEvents"] == 1
    assert event.raw_value == 2
    assert event.score_delta == -2


def test_map_competition_result_to_bonus_event(test_db: Session):
    member = _member(test_db)
    cycle = _cycle(test_db)
    _seed_phase5_criteria(test_db)
    _competition_result(test_db, member, bonus_kpi=2.5)

    summary = EvaluationLegacyMigrationService(test_db).migrate(
        cycle.id,
        mode="sandbox",
        migration_batch_id="batch-competition",
    )
    test_db.commit()
    event = test_db.scalar(
        select(EvaluationScoreEvent).where(
            EvaluationScoreEvent.source_type == "COMPETITION_RESULT"
        )
    )

    assert summary["createdScoreEvents"] == 1
    assert event.criterion_code == "III-A.5"
    assert event.score_delta == 2.5


def test_kpi_is_snapshot_not_total_score(test_db: Session):
    member = _member(test_db)
    cycle = _cycle(test_db)
    _seed_phase5_criteria(test_db)
    _discipline_record(test_db, member, kpi=120)

    summary = EvaluationLegacyMigrationService(test_db).migrate(
        cycle.id,
        mode="sandbox",
        migration_batch_id="batch-kpi",
    )
    test_db.commit()
    evaluation = test_db.scalar(select(MemberEvaluation))

    assert evaluation is None
    assert summary["manualReviewQueue"][0]["issueCode"] == "LEGACY_KPI_OUT_OF_RANGE"


def test_migration_is_idempotent_for_score_events(test_db: Session):
    member = _member(test_db)
    cycle = _cycle(test_db)
    _seed_phase5_criteria(test_db)
    _discipline_record(test_db, member, absents=1)
    service = EvaluationLegacyMigrationService(test_db)

    first = service.migrate(cycle.id, mode="sandbox", migration_batch_id="batch-idem")
    test_db.commit()
    second = service.migrate(cycle.id, mode="sandbox", migration_batch_id="batch-idem")

    assert first["createdScoreEvents"] == 1
    assert second["createdScoreEvents"] == 0
    assert second["skipped"] >= 1


def test_migration_is_idempotent_for_discipline_cases(test_db: Session):
    member = _member(test_db)
    cycle = _cycle(test_db)
    _seed_phase5_criteria(test_db)
    _discipline_record(test_db, member, discipline_level="Nhac nho")
    service = EvaluationLegacyMigrationService(test_db)

    first = service.migrate(cycle.id, mode="sandbox", migration_batch_id="batch-case")
    test_db.commit()
    second = service.migrate(cycle.id, mode="sandbox", migration_batch_id="batch-case")

    assert first["createdDisciplineCases"] == 1
    assert second["createdDisciplineCases"] == 0


def test_conflicting_existing_event_is_reported(test_db: Session):
    member = _member(test_db)
    cycle = _cycle(test_db)
    criterion = _criterion(test_db, "I.2", component="I", max_score=30)
    record = _discipline_record(test_db, member, absents=2)
    test_db.add(
        EvaluationScoreEvent(
            cycle_id=cycle.id,
            member_id=member.id,
            criterion_id=criterion.id,
            criterion_code=criterion.code,
            component=criterion.component,
            event_type="LEGACY_IMPORT",
            source_type="LEGACY_DISCIPLINE_RECORD",
            source_id=record.id,
            score_delta=-5,
        )
    )
    test_db.commit()

    summary = EvaluationLegacyMigrationService(test_db).migrate(
        cycle.id,
        mode="sandbox",
        migration_batch_id="batch-conflict",
    )

    assert summary["warnings"][0]["code"] == "CONFLICTING_LEGACY_MAPPING"


def test_dry_run_does_not_commit_records(test_db: Session):
    member = _member(test_db)
    cycle = _cycle(test_db)
    _seed_phase5_criteria(test_db)
    _discipline_record(test_db, member, absents=1, discipline_level="Nhac nho")

    summary = EvaluationLegacyMigrationService(test_db).migrate(
        cycle.id,
        mode="dry_run",
        migration_batch_id="batch-dry",
    )

    assert summary["createdScoreEvents"] == 1
    assert summary["createdDisciplineCases"] == 1
    assert test_db.scalar(select(EvaluationScoreEvent)) is None
    assert test_db.scalar(select(DisciplineCase)) is None


def test_soft_rollback_voids_migrated_events(test_db: Session):
    member = _member(test_db)
    cycle = _cycle(test_db)
    _seed_phase5_criteria(test_db)
    _discipline_record(test_db, member, absents=1)
    service = EvaluationLegacyMigrationService(test_db)
    service.migrate(cycle.id, mode="sandbox", migration_batch_id="batch-rollback")
    test_db.commit()

    result = service.soft_rollback("batch-rollback")
    test_db.commit()
    event = test_db.scalar(select(EvaluationScoreEvent))
    evidence = test_db.scalar(select(EvaluationEvidence))

    assert result["voidedScoreEvents"] == 1
    assert result["rejectedEvidence"] == 1
    assert event.is_void is True
    assert evidence.status == "REJECTED"


def test_rollback_uses_migration_batch_id(test_db: Session):
    member = _member(test_db)
    cycle = _cycle(test_db)
    _seed_phase5_criteria(test_db)
    first_record = _discipline_record(test_db, member, absents=1)
    service = EvaluationLegacyMigrationService(test_db)
    service.migrate(cycle.id, mode="sandbox", migration_batch_id="batch-a")
    test_db.commit()
    first_record.absents = 2
    test_db.commit()
    service.migrate(cycle.id, mode="sandbox", migration_batch_id="batch-b")
    test_db.commit()

    result = service.soft_rollback("batch-a")

    assert result["voidedScoreEvents"] == 1


def test_legacy_get_still_works_during_stage_1(
    client: TestClient,
    test_db: Session,
    monkeypatch,
):
    monkeypatch.setattr("app.core.config.DISCIPLINE_LEGACY_READ_ONLY", False)
    monkeypatch.setattr("app.core.config.DISCIPLINE_LEGACY_DEPRECATION_HEADER", False)
    user = _user(test_db, "legacy_get", "bcn")

    response = client.get("/api/v1/discipline-records", headers=_auth_header(user.id))

    assert response.status_code == 200


def test_legacy_mutation_rejected_in_read_only_mode(
    client: TestClient,
    test_db: Session,
    monkeypatch,
):
    monkeypatch.setattr("app.core.config.DISCIPLINE_LEGACY_READ_ONLY", True)
    user = _user(test_db, "legacy_readonly", "bcn")

    response = client.post(
        "/api/v1/discipline-records",
        json={
            "memberId": None,
            "mssv": "RO001",
            "name": "Read Only",
            "absents": 0,
            "kpi": 0,
            "disciplineLevel": "Khong",
        },
        headers=_auth_header(user.id),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "DISCIPLINE_LEGACY_READ_ONLY"


def test_legacy_response_contains_deprecation_header(
    client: TestClient,
    test_db: Session,
    monkeypatch,
):
    monkeypatch.setattr("app.core.config.DISCIPLINE_LEGACY_DEPRECATION_HEADER", True)
    user = _user(test_db, "legacy_header", "bcn")

    response = client.get("/api/v1/discipline-records/stats", headers=_auth_header(user.id))

    assert response.status_code == 200
    assert response.headers["X-MTEC-Deprecated"] == "true"


def test_discipline_level_mapping_handles_vietnamese_text():
    mapping = map_discipline_level("Cảnh cáo Lần 1")

    assert mapping["caseType"] == "WARNING"
