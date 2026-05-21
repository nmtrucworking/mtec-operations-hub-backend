from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.evaluation_constants import (
    COMPONENT_I,
    COMPONENT_II,
    COMPONENT_III_A,
    COMPONENT_III_B,
)
from app.models import (
    EvaluationCriterion,
    EvaluationCycle,
    EvaluationScoreEvent,
    Member,
    MemberCycleRole,
    MemberEvaluation,
)
from app.services.evaluation_calculator import EvaluationCalculatorService
from app.services.evaluation_criteria_seed import (
    DEFAULT_EVALUATION_CRITERIA_2026,
    EvaluationCriteriaSeedService,
)
from app.services.evaluation_errors import EvaluationWeightError


def _cycle(test_db: Session) -> EvaluationCycle:
    cycle = EvaluationCycle(
        code="2026-05-CALC",
        name="Calculation cycle",
        type="MONTHLY",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
    )
    test_db.add(cycle)
    test_db.flush()
    return cycle


def _member(test_db: Session, *, mssv: str = "CALC001", ban: str | None = None) -> Member:
    member = Member(mssv=mssv, name="Calculator Tester", ban=ban)
    test_db.add(member)
    test_db.flush()
    return member


def _criterion(
    test_db: Session,
    *,
    code: str,
    component: str,
    max_score: float,
    unit_code: str | None = None,
) -> EvaluationCriterion:
    criterion = EvaluationCriterion(
        code=code,
        name=code,
        component=component,
        unit_scope="UNIT_SPECIFIC" if unit_code else "ALL",
        unit_code=unit_code,
        max_score=max_score,
        score_method="MANUAL",
        requires_evidence=False,
    )
    test_db.add(criterion)
    test_db.flush()
    return criterion


def _event(
    test_db: Session,
    *,
    cycle: EvaluationCycle,
    member: Member,
    criterion: EvaluationCriterion,
    score_delta: float,
    raw_value: float | None = None,
) -> EvaluationScoreEvent:
    event = EvaluationScoreEvent(
        cycle_id=cycle.id,
        member_id=member.id,
        criterion_id=criterion.id,
        criterion_code=criterion.code,
        component=criterion.component,
        unit_code=criterion.unit_code,
        event_type="MANUAL_SCORE",
        raw_value=raw_value,
        score_delta=score_delta,
    )
    test_db.add(event)
    test_db.flush()
    return event


def test_criterion_score_is_capped_by_max_score(test_db: Session):
    cycle = _cycle(test_db)
    member = _member(test_db)
    criterion = _criterion(
        test_db, code="I.1", component=COMPONENT_I, max_score=5.0
    )
    _event(test_db, cycle=cycle, member=member, criterion=criterion, score_delta=12.0)

    result = EvaluationCalculatorService(test_db).preview_member(cycle.id, member.id)

    assert result["breakdowns"][0]["rawScore"] == 12.0
    assert result["breakdowns"][0]["finalScore"] == 5.0
    assert result["breakdowns"][0]["capApplied"] is True


def test_criterion_score_never_negative(test_db: Session):
    cycle = _cycle(test_db)
    member = _member(test_db)
    criterion = _criterion(
        test_db, code="I.2", component=COMPONENT_I, max_score=7.0
    )
    _event(test_db, cycle=cycle, member=member, criterion=criterion, score_delta=-4.0)

    result = EvaluationCalculatorService(test_db).preview_member(cycle.id, member.id)

    assert result["breakdowns"][0]["finalScore"] == 0.0
    assert result["totalScore"] == 0.0


def test_component_scores_are_capped(test_db: Session):
    cycle = _cycle(test_db)
    member = _member(test_db, ban="BCNg")
    criteria = [
        _criterion(test_db, code="I.MAX", component=COMPONENT_I, max_score=99.0),
        _criterion(test_db, code="II.MAX", component=COMPONENT_II, max_score=99.0),
        _criterion(test_db, code="III-A.MAX", component=COMPONENT_III_A, max_score=99.0),
        _criterion(
            test_db,
            code="III-B.BCNg.MAX",
            component=COMPONENT_III_B,
            max_score=99.0,
            unit_code="BCNg",
        ),
    ]
    for criterion in criteria:
        _event(test_db, cycle=cycle, member=member, criterion=criterion, score_delta=99.0)

    result = EvaluationCalculatorService(test_db).preview_member(cycle.id, member.id)

    assert result["componentScores"][COMPONENT_I] == 30.0
    assert result["componentScores"][COMPONENT_II] == 20.0
    assert result["componentScores"][COMPONENT_III_A] == 30.0
    assert result["componentScores"][COMPONENT_III_B] == 20.0


def test_total_score_is_capped_at_100(test_db: Session):
    cycle = _cycle(test_db)
    member = _member(test_db, ban="BCNg")
    criteria = [
        _criterion(test_db, code="I.MAX", component=COMPONENT_I, max_score=99.0),
        _criterion(test_db, code="II.MAX", component=COMPONENT_II, max_score=99.0),
        _criterion(test_db, code="III-A.MAX", component=COMPONENT_III_A, max_score=99.0),
        _criterion(
            test_db,
            code="III-B.BCNg.MAX",
            component=COMPONENT_III_B,
            max_score=99.0,
            unit_code="BCNg",
        ),
    ]
    for criterion in criteria:
        _event(test_db, cycle=cycle, member=member, criterion=criterion, score_delta=99.0)

    result = EvaluationCalculatorService(test_db).compute_member(cycle.id, member.id)
    stored = test_db.scalar(
        select(MemberEvaluation).where(MemberEvaluation.member_id == member.id)
    )

    assert result["totalScore"] == 100.0
    assert stored is not None
    assert stored.total_score == 100.0
    assert stored.final_classification == "EXCELLENT"


def test_compute_single_unit_iii_b(test_db: Session):
    cycle = _cycle(test_db)
    member = _member(test_db, ban="BCNg")
    criterion = _criterion(
        test_db,
        code="III-B.BCNg.01",
        component=COMPONENT_III_B,
        max_score=20.0,
        unit_code="BCNg",
    )
    _event(test_db, cycle=cycle, member=member, criterion=criterion, score_delta=17.0)

    result = EvaluationCalculatorService(test_db).preview_member(cycle.id, member.id)

    assert result["componentScores"][COMPONENT_III_B] == 17.0


def test_compute_multi_unit_iii_b_weighted(test_db: Session):
    cycle = _cycle(test_db)
    member = _member(test_db, mssv="CALC002")
    criterion_bcng = _criterion(
        test_db,
        code="III-B.BCNg.01",
        component=COMPONENT_III_B,
        max_score=20.0,
        unit_code="BCNg",
    )
    criterion_btt = _criterion(
        test_db,
        code="III-B.BTT.01",
        component=COMPONENT_III_B,
        max_score=20.0,
        unit_code="BTT",
    )
    test_db.add_all(
        [
            MemberCycleRole(
                cycle_id=cycle.id,
                member_id=member.id,
                unit_code="BCNg",
                role_type="PRIMARY",
                participation_weight=0.7,
                is_primary=True,
            ),
            MemberCycleRole(
                cycle_id=cycle.id,
                member_id=member.id,
                unit_code="BTT",
                role_type="SECONDARY",
                participation_weight=0.3,
                is_primary=False,
            ),
        ]
    )
    _event(test_db, cycle=cycle, member=member, criterion=criterion_bcng, score_delta=18.0)
    _event(test_db, cycle=cycle, member=member, criterion=criterion_btt, score_delta=16.0)
    test_db.flush()

    result = EvaluationCalculatorService(test_db).preview_member(cycle.id, member.id)

    assert result["componentScores"][COMPONENT_III_B] == pytest.approx(17.4)


def test_invalid_multi_unit_weight_raises_error(test_db: Session):
    cycle = _cycle(test_db)
    member = _member(test_db, mssv="CALC003")
    criterion = _criterion(
        test_db,
        code="III-B.BCNg.01",
        component=COMPONENT_III_B,
        max_score=20.0,
        unit_code="BCNg",
    )
    test_db.add_all(
        [
            MemberCycleRole(
                cycle_id=cycle.id,
                member_id=member.id,
                unit_code="BCNg",
                role_type="PRIMARY",
                participation_weight=0.8,
                is_primary=True,
            ),
            MemberCycleRole(
                cycle_id=cycle.id,
                member_id=member.id,
                unit_code="BTT",
                role_type="SECONDARY",
                participation_weight=0.3,
                is_primary=False,
            ),
        ]
    )
    _event(test_db, cycle=cycle, member=member, criterion=criterion, score_delta=18.0)
    test_db.flush()

    with pytest.raises(EvaluationWeightError):
        EvaluationCalculatorService(test_db).preview_member(cycle.id, member.id)


def test_missing_primary_role_fallback_to_member_ban(test_db: Session):
    cycle = _cycle(test_db)
    member = _member(test_db, mssv="CALC004", ban="BTT")
    criterion = _criterion(
        test_db,
        code="III-B.BTT.01",
        component=COMPONENT_III_B,
        max_score=20.0,
        unit_code="BTT",
    )
    _event(test_db, cycle=cycle, member=member, criterion=criterion, score_delta=14.0)

    result = EvaluationCalculatorService(test_db).preview_member(cycle.id, member.id)

    assert result["componentScores"][COMPONENT_III_B] == 14.0


def test_seed_default_criteria_is_idempotent(test_db: Session):
    service = EvaluationCriteriaSeedService(test_db)

    first = service.seed_default_criteria_2026()
    second = service.seed_default_criteria_2026()
    count = test_db.scalar(select(func.count()).select_from(EvaluationCriterion))

    assert first["insertedCount"] == len(DEFAULT_EVALUATION_CRITERIA_2026)
    assert second["insertedCount"] == 0
    assert second["updatedCount"] == len(DEFAULT_EVALUATION_CRITERIA_2026)
    assert count == len(DEFAULT_EVALUATION_CRITERIA_2026)
