from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.models import (
    EvaluationCriterion,
    EvaluationCycle,
    EvaluationEvidence,
    EvaluationScoreEvent,
    Member,
)
from app.services.evaluation_errors import EvaluationEvidenceError
from app.services.evaluation_evidence import EvidenceValidationService


def _base_objects(test_db: Session, *, requires_evidence: bool = True):
    cycle = EvaluationCycle(
        code="2026-05-EVIDENCE",
        name="Evidence cycle",
        type="MONTHLY",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
    )
    member = Member(mssv="EVID001", name="Evidence Tester")
    criterion = EvaluationCriterion(
        code="I.1",
        name="Attendance",
        component="I",
        unit_scope="ALL",
        max_score=10.0,
        score_method="MANUAL",
        requires_evidence=requires_evidence,
    )
    test_db.add_all([cycle, member, criterion])
    test_db.flush()
    event = EvaluationScoreEvent(
        cycle_id=cycle.id,
        member_id=member.id,
        criterion_id=criterion.id,
        criterion_code=criterion.code,
        component=criterion.component,
        event_type="BASE",
        score_delta=8.0,
    )
    test_db.add(event)
    test_db.flush()
    return cycle, member, criterion, event


def test_event_with_required_evidence_passes_when_evidence_exists(test_db: Session):
    _, member, criterion, event = _base_objects(test_db)
    test_db.add(
        EvaluationEvidence(
            cycle_id=event.cycle_id,
            member_id=member.id,
            criterion_id=criterion.id,
            score_event_id=event.id,
            evidence_type="LINK",
            title="Evidence",
            status="PENDING",
        )
    )
    test_db.flush()
    service = EvidenceValidationService(test_db)

    warnings = service.validate_score_events([event], strict=True)

    assert warnings == []
    assert service.count_evidence_for_event(event.id) == 1


def test_event_with_required_evidence_fails_when_missing(test_db: Session):
    *_, event = _base_objects(test_db)
    service = EvidenceValidationService(test_db)

    with pytest.raises(EvaluationEvidenceError):
        service.validate_score_events([event], strict=True)


def test_event_without_required_evidence_passes(test_db: Session):
    *_, event = _base_objects(test_db, requires_evidence=False)
    service = EvidenceValidationService(test_db)

    warnings = service.validate_score_events([event], strict=True)

    assert warnings == []


def test_approval_mode_requires_verified_evidence(test_db: Session):
    _, member, criterion, event = _base_objects(test_db)
    test_db.add(
        EvaluationEvidence(
            cycle_id=event.cycle_id,
            member_id=member.id,
            criterion_id=criterion.id,
            score_event_id=event.id,
            evidence_type="LINK",
            title="Pending evidence",
            status="PENDING",
        )
    )
    test_db.flush()
    service = EvidenceValidationService(test_db)

    assert service.has_valid_evidence_for_event(event.id, mode="draft") is True
    assert service.has_valid_evidence_for_event(event.id, mode="approval") is False
    with pytest.raises(EvaluationEvidenceError):
        service.validate_score_events([event], strict=True, mode="approval")
