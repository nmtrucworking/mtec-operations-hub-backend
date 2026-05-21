from datetime import date

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    EvaluationCriterion,
    EvaluationCycle,
    EvaluationEvidence,
    EvaluationScoreEvent,
    Member,
    MemberCycleRole,
    MemberEvaluation,
    User,
)


EXPECTED_EVALUATION_TABLES = {
    "evaluation_cycles",
    "evaluation_criteria",
    "evaluation_score_events",
    "evaluation_evidence",
    "member_evaluations",
    "member_evaluation_breakdowns",
    "member_cycle_roles",
    "evaluation_appeals",
    "discipline_cases",
}


def _cycle(code: str = "2026-05-MONTHLY") -> EvaluationCycle:
    return EvaluationCycle(
        code=code,
        name="May 2026 monthly evaluation",
        type="MONTHLY",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
    )


def _criterion(code: str = "I.1") -> EvaluationCriterion:
    return EvaluationCriterion(
        code=code,
        name="Attendance ratio",
        component="I",
        unit_scope="ALL",
        max_score=10.0,
        score_method="RATIO",
        effective_from=date(2026, 5, 1),
    )


def _member(mssv: str = "MTEC001") -> Member:
    return Member(mssv=mssv, name="Schema Tester")


def _user(username: str = "schema-admin") -> User:
    return User(
        username=username,
        password_hash="hashed-password",
        full_name="Schema Admin",
        role="bcn",
    )


def test_evaluation_core_tables_exist(test_db: Session):
    inspector = inspect(test_db.bind)
    table_names = set(inspector.get_table_names())

    assert EXPECTED_EVALUATION_TABLES.issubset(table_names)
    assert "discipline_records" in table_names


def test_evaluation_schema_has_core_foreign_keys(test_db: Session):
    inspector = inspect(test_db.bind)

    score_event_fks = {
        (tuple(fk["constrained_columns"]), fk["referred_table"])
        for fk in inspector.get_foreign_keys("evaluation_score_events")
    }
    evidence_fks = {
        (tuple(fk["constrained_columns"]), fk["referred_table"])
        for fk in inspector.get_foreign_keys("evaluation_evidence")
    }
    member_evaluation_fks = {
        (tuple(fk["constrained_columns"]), fk["referred_table"])
        for fk in inspector.get_foreign_keys("member_evaluations")
    }

    assert (("cycle_id",), "evaluation_cycles") in score_event_fks
    assert (("member_id",), "members") in score_event_fks
    assert (("criterion_id",), "evaluation_criteria") in score_event_fks
    assert (("score_event_id",), "evaluation_score_events") in evidence_fks
    assert (("cycle_id",), "evaluation_cycles") in member_evaluation_fks
    assert (("member_id",), "members") in member_evaluation_fks


def test_evaluation_schema_has_query_indexes(test_db: Session):
    inspector = inspect(test_db.bind)
    score_event_indexes = {
        index["name"] for index in inspector.get_indexes("evaluation_score_events")
    }
    member_evaluation_indexes = {
        index["name"] for index in inspector.get_indexes("member_evaluations")
    }

    assert "ix_evaluation_score_events_cycle_id" in score_event_indexes
    assert "ix_evaluation_score_events_member_id" in score_event_indexes
    assert "ix_evaluation_score_events_criterion_code" in score_event_indexes
    assert "ix_evaluation_score_events_unit_code" in score_event_indexes
    assert "ix_member_evaluations_status" in member_evaluation_indexes
    assert "ix_member_evaluations_total_score" in member_evaluation_indexes


def test_create_evaluation_cycle(test_db: Session):
    cycle = _cycle()

    test_db.add(cycle)
    test_db.commit()
    test_db.refresh(cycle)

    assert cycle.id
    assert cycle.status == "DRAFT"
    assert cycle.created_at is not None
    assert cycle.updated_at is not None


def test_cycle_code_unique(test_db: Session):
    test_db.add(_cycle("2026-05-UNIQUE"))
    test_db.commit()

    test_db.add(_cycle("2026-05-UNIQUE"))
    with pytest.raises(IntegrityError):
        test_db.commit()
    test_db.rollback()


def test_create_criterion(test_db: Session):
    criterion = _criterion()

    test_db.add(criterion)
    test_db.commit()
    test_db.refresh(criterion)

    assert criterion.id
    assert criterion.requires_evidence is True
    assert criterion.is_active is True
    assert criterion.sort_order == 0


def test_member_evaluation_unique_per_cycle_member(test_db: Session):
    cycle = _cycle("2026-06-MONTHLY")
    member = _member("MTEC002")
    test_db.add_all([cycle, member])
    test_db.flush()

    test_db.add(MemberEvaluation(cycle_id=cycle.id, member_id=member.id))
    test_db.commit()

    test_db.add(MemberEvaluation(cycle_id=cycle.id, member_id=member.id))
    with pytest.raises(IntegrityError):
        test_db.commit()
    test_db.rollback()


def test_score_event_can_attach_evidence_and_role(test_db: Session):
    user = _user()
    member = _member("MTEC003")
    cycle = _cycle("2026-07-MONTHLY")
    criterion = _criterion("I.2")
    test_db.add_all([user, member, cycle, criterion])
    test_db.flush()

    role = MemberCycleRole(
        cycle_id=cycle.id,
        member_id=member.id,
        unit_code="BCNg",
        role_type="PRIMARY",
        participation_weight=1.0,
        is_primary=True,
        assigned_by_user_id=user.id,
    )
    score_event = EvaluationScoreEvent(
        cycle_id=cycle.id,
        member_id=member.id,
        criterion_id=criterion.id,
        criterion_code=criterion.code,
        component=criterion.component,
        unit_code="BCNg",
        event_type="BASE",
        source_type="ATTENDANCE",
        source_id="meeting-1",
        score_delta=10.0,
        max_score_snapshot=criterion.max_score,
        recorded_by_user_id=user.id,
    )
    test_db.add_all([role, score_event])
    test_db.flush()

    evidence = EvaluationEvidence(
        cycle_id=cycle.id,
        member_id=member.id,
        criterion_id=criterion.id,
        score_event_id=score_event.id,
        evidence_type="LINK",
        title="Attendance sheet",
        url="https://example.test/attendance",
        submitted_by_user_id=user.id,
    )
    test_db.add(evidence)
    test_db.commit()
    test_db.refresh(evidence)

    assert role.id
    assert score_event.is_void is False
    assert evidence.status == "PENDING"
    assert evidence.score_event_id == score_event.id
