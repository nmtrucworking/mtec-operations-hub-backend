import json
from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import (
    EvaluationAppeal,
    EvaluationCriterion,
    EvaluationCycle,
    EvaluationScoreEvent,
    Member,
    MemberEvaluation,
    User,
)


def _auth_header(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def _user(test_db: Session, username: str, role: str) -> User:
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


def _member(test_db: Session, mssv: str, *, ban: str | None = None) -> Member:
    member = Member(mssv=mssv, name=f"Member {mssv}", ban=ban)
    test_db.add(member)
    test_db.commit()
    return member


def _cycle(
    test_db: Session,
    code: str,
    *,
    status: str = "SCORING",
) -> EvaluationCycle:
    cycle = EvaluationCycle(
        code=code,
        name=f"Cycle {code}",
        type="MONTHLY",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
        status=status,
    )
    test_db.add(cycle)
    test_db.commit()
    return cycle


def _criterion(
    test_db: Session,
    code: str = "I.P4",
    *,
    component: str = "I",
    max_score: float = 20.0,
) -> EvaluationCriterion:
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


def _member_evaluation(
    test_db: Session,
    cycle: EvaluationCycle,
    member: Member,
    *,
    status: str = "COMPUTED",
    total_score: float = 10.0,
) -> MemberEvaluation:
    row = MemberEvaluation(
        cycle_id=cycle.id,
        member_id=member.id,
        total_score=total_score,
        final_classification="PASSED",
        status=status,
    )
    test_db.add(row)
    test_db.commit()
    return row


def _appeal(
    test_db: Session,
    cycle: EvaluationCycle,
    member: Member,
    *,
    status: str = "PENDING",
    criterion: EvaluationCriterion | None = None,
) -> EvaluationAppeal:
    appeal = EvaluationAppeal(
        cycle_id=cycle.id,
        member_id=member.id,
        criterion_id=criterion.id if criterion else None,
        criterion_code=criterion.code if criterion else None,
        appeal_type="PROFESSIONAL_SCORE",
        content="Please review",
        status=status,
    )
    test_db.add(appeal)
    test_db.commit()
    return appeal


def _score_event(
    test_db: Session,
    cycle: EvaluationCycle,
    member: Member,
    criterion: EvaluationCriterion,
    *,
    score_delta: float = 4.0,
) -> EvaluationScoreEvent:
    event = EvaluationScoreEvent(
        cycle_id=cycle.id,
        member_id=member.id,
        criterion_id=criterion.id,
        criterion_code=criterion.code,
        component=criterion.component,
        event_type="BASE",
        score_delta=score_delta,
    )
    test_db.add(event)
    test_db.commit()
    return event


def test_open_member_review_requires_operator_role(client: TestClient, test_db: Session):
    member_user = _user(test_db, "phase4_member_open", "member")
    cycle = _cycle(test_db, "P4-OPEN-DENIED")

    response = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/review/open",
        json={},
        headers=_auth_header(member_user.id),
    )

    assert response.status_code == 403


def test_open_member_review_sets_cycle_and_member_statuses(
    client: TestClient,
    test_db: Session,
):
    operator = _user(test_db, "phase4_operator_open", "bvh_discipline")
    member = _member(test_db, "P4OPEN001")
    cycle = _cycle(test_db, "P4-OPEN")
    _member_evaluation(test_db, cycle, member)

    response = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/review/open",
        json={},
        headers=_auth_header(operator.id),
    )
    stored_eval = test_db.scalar(
        select(MemberEvaluation).where(MemberEvaluation.cycle_id == cycle.id)
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "MEMBER_REVIEW"
    assert response.json()["meta"]["updatedMembers"] == 1
    assert stored_eval.status == "UNDER_REVIEW"


def test_close_review_with_no_appeals_moves_ready_for_approval(
    client: TestClient,
    test_db: Session,
):
    operator = _user(test_db, "phase4_operator_close", "bvh_hr")
    member = _member(test_db, "P4CLOSE001")
    cycle = _cycle(test_db, "P4-CLOSE-NO-APPEAL", status="MEMBER_REVIEW")
    _member_evaluation(test_db, cycle, member, status="UNDER_REVIEW")

    response = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/review/close",
        headers=_auth_header(operator.id),
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "READY_FOR_APPROVAL"
    assert response.json()["meta"]["openAppeals"] == 0


def test_close_review_with_open_appeals_moves_appeal_resolution(
    client: TestClient,
    test_db: Session,
):
    operator = _user(test_db, "phase4_operator_close_appeal", "bvh_hr")
    member = _member(test_db, "P4CLOSE002")
    cycle = _cycle(test_db, "P4-CLOSE-APPEAL", status="MEMBER_REVIEW")
    _member_evaluation(test_db, cycle, member, status="UNDER_REVIEW")
    _appeal(test_db, cycle, member)

    response = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/review/close",
        headers=_auth_header(operator.id),
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "APPEAL_RESOLUTION"
    assert response.json()["meta"]["openAppeals"] == 1


def test_member_can_create_own_appeal_during_review(
    client: TestClient,
    test_db: Session,
):
    member = _member(test_db, "P4OWN001")
    owner = _user(test_db, "P4OWN001", "member")
    cycle = _cycle(test_db, "P4-OWN-APPEAL", status="MEMBER_REVIEW")
    _member_evaluation(test_db, cycle, member, status="UNDER_REVIEW")

    response = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/appeals",
        json={
            "memberId": member.id,
            "appealType": "PROFESSIONAL_SCORE",
            "content": "Please review my score",
        },
        headers=_auth_header(owner.id),
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "PENDING"
    assert test_db.get(EvaluationCycle, cycle.id).status == "MEMBER_REVIEW"


def test_member_cannot_create_appeal_for_other_member(
    client: TestClient,
    test_db: Session,
):
    owner = _user(test_db, "P4OWNER002", "member")
    other_member = _member(test_db, "P4OTHER002")
    cycle = _cycle(test_db, "P4-OTHER-APPEAL", status="MEMBER_REVIEW")

    response = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/appeals",
        json={
            "memberId": other_member.id,
            "appealType": "PROFESSIONAL_SCORE",
            "content": "Try to review another member",
        },
        headers=_auth_header(owner.id),
    )

    assert response.status_code == 403


def test_appeal_after_review_deadline_is_rejected(
    client: TestClient,
    test_db: Session,
):
    member = _member(test_db, "P4LATE001")
    owner = _user(test_db, "P4LATE001", "member")
    deadline = datetime.now(UTC) - timedelta(days=1)
    cycle = _cycle(test_db, "P4-LATE-APPEAL", status="MEMBER_REVIEW")
    cycle.metadata_json = json.dumps({"review": {"deadline": deadline.isoformat()}})
    test_db.commit()

    response = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/appeals",
        json={
            "memberId": member.id,
            "appealType": "PROFESSIONAL_SCORE",
            "content": "Late appeal",
        },
        headers=_auth_header(owner.id),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "EVALUATION_REVIEW_WINDOW_CLOSED"


def test_manager_can_start_appeal_review(client: TestClient, test_db: Session):
    manager = _user(test_db, "phase4_manager_start", "bvh_hr")
    member = _member(test_db, "P4START001")
    cycle = _cycle(test_db, "P4-START", status="APPEAL_RESOLUTION")
    appeal = _appeal(test_db, cycle, member)

    response = client.post(
        f"/api/v2/evaluations/appeals/{appeal.id}/start-review",
        headers=_auth_header(manager.id),
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "IN_REVIEW"


def test_request_more_evidence_changes_status(client: TestClient, test_db: Session):
    manager = _user(test_db, "phase4_manager_evidence", "bvh_hr")
    member = _member(test_db, "P4EVID001")
    cycle = _cycle(test_db, "P4-REQ-EVIDENCE", status="APPEAL_RESOLUTION")
    appeal = _appeal(test_db, cycle, member, status="IN_REVIEW")

    response = client.post(
        f"/api/v2/evaluations/appeals/{appeal.id}/request-evidence",
        json={"note": "Need more proof"},
        headers=_auth_header(manager.id),
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "NEEDS_MORE_EVIDENCE"


def test_cancel_pending_appeal_by_owner(client: TestClient, test_db: Session):
    member = _member(test_db, "P4CANCEL001")
    owner = _user(test_db, "P4CANCEL001", "member")
    cycle = _cycle(test_db, "P4-CANCEL", status="APPEAL_RESOLUTION")
    appeal = _appeal(test_db, cycle, member)

    response = client.post(
        f"/api/v2/evaluations/appeals/{appeal.id}/cancel",
        json={"reason": "I found the answer"},
        headers=_auth_header(owner.id),
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "CANCELLED"


def test_cannot_cancel_resolved_appeal(client: TestClient, test_db: Session):
    member = _member(test_db, "P4CANCEL002")
    owner = _user(test_db, "P4CANCEL002", "member")
    cycle = _cycle(test_db, "P4-CANCEL-RESOLVED", status="APPEAL_RESOLUTION")
    appeal = _appeal(test_db, cycle, member, status="REJECTED")

    response = client.post(
        f"/api/v2/evaluations/appeals/{appeal.id}/cancel",
        json={"reason": "Too late"},
        headers=_auth_header(owner.id),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "EVALUATION_APPEAL_ALREADY_RESOLVED"


def test_accept_appeal_creates_adjustment_event(client: TestClient, test_db: Session):
    manager = _user(test_db, "phase4_manager_accept", "bvh_hr")
    member = _member(test_db, "P4ACCEPT001")
    cycle = _cycle(test_db, "P4-ACCEPT", status="APPEAL_RESOLUTION")
    criterion = _criterion(test_db, "P4.ACCEPT")
    _member_evaluation(test_db, cycle, member, status="APPEALED")
    appeal = _appeal(test_db, cycle, member, status="IN_REVIEW", criterion=criterion)

    response = client.post(
        f"/api/v2/evaluations/appeals/{appeal.id}/resolve",
        json={
            "decision": "ACCEPTED",
            "resolutionNote": "Accepted adjustment",
            "targetCriterionCode": criterion.code,
            "adjustedScoreDelta": 3,
            "createAdjustmentEvent": True,
        },
        headers=_auth_header(manager.id),
    )
    event_count = test_db.scalar(
        select(func.count())
        .select_from(EvaluationScoreEvent)
        .where(EvaluationScoreEvent.source_type == "APPEAL")
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ACCEPTED"
    assert response.json()["meta"]["adjustmentEvent"]["scoreDelta"] == 3
    assert event_count == 1


def test_reject_appeal_does_not_create_adjustment_event(
    client: TestClient,
    test_db: Session,
):
    manager = _user(test_db, "phase4_manager_reject", "bvh_hr")
    member = _member(test_db, "P4REJECT001")
    cycle = _cycle(test_db, "P4-REJECT", status="APPEAL_RESOLUTION")
    appeal = _appeal(test_db, cycle, member, status="IN_REVIEW")

    response = client.post(
        f"/api/v2/evaluations/appeals/{appeal.id}/resolve",
        json={
            "decision": "REJECTED",
            "resolutionNote": "Original data is correct",
        },
        headers=_auth_header(manager.id),
    )
    event_count = test_db.scalar(
        select(func.count())
        .select_from(EvaluationScoreEvent)
        .where(EvaluationScoreEvent.source_type == "APPEAL")
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "REJECTED"
    assert event_count == 0


def test_resolve_appeal_recomputes_member(client: TestClient, test_db: Session):
    manager = _user(test_db, "phase4_manager_recompute", "bvh_hr")
    member = _member(test_db, "P4RECOMP001")
    cycle = _cycle(test_db, "P4-RECOMPUTE", status="APPEAL_RESOLUTION")
    criterion = _criterion(test_db, "P4.RECOMPUTE")
    _score_event(test_db, cycle, member, criterion, score_delta=4)
    _member_evaluation(test_db, cycle, member, status="APPEALED", total_score=4)
    appeal = _appeal(test_db, cycle, member, status="IN_REVIEW", criterion=criterion)

    response = client.post(
        f"/api/v2/evaluations/appeals/{appeal.id}/resolve",
        json={
            "decision": "PARTIALLY_ACCEPTED",
            "resolutionNote": "Add partial score",
            "targetCriterionCode": criterion.code,
            "adjustedScoreDelta": 3,
            "createAdjustmentEvent": True,
            "recomputeMember": True,
        },
        headers=_auth_header(manager.id),
    )
    stored_eval = test_db.scalar(
        select(MemberEvaluation).where(MemberEvaluation.member_id == member.id)
    )

    assert response.status_code == 200
    assert stored_eval.total_score == 7
    assert stored_eval.status == "APPEAL_RESOLVED"


def test_ready_for_approval_requires_no_open_appeals(
    client: TestClient,
    test_db: Session,
):
    operator = _user(test_db, "phase4_ready_operator", "bvh_discipline")
    member = _member(test_db, "P4READY001")
    cycle = _cycle(test_db, "P4-READY-OPEN", status="APPEAL_RESOLUTION")
    _member_evaluation(test_db, cycle, member, status="APPEALED")
    _appeal(test_db, cycle, member)

    response = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/ready-for-approval",
        headers=_auth_header(operator.id),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "EVALUATION_OPEN_APPEALS_EXIST"


def test_approve_cycle_requires_bcn(client: TestClient, test_db: Session):
    operator = _user(test_db, "phase4_approve_operator", "bvh_discipline")
    member = _member(test_db, "P4APPROVE001")
    cycle = _cycle(test_db, "P4-APPROVE-DENIED", status="READY_FOR_APPROVAL")
    _member_evaluation(test_db, cycle, member, status="APPEAL_RESOLVED")

    response = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/approve",
        json={},
        headers=_auth_header(operator.id),
    )

    assert response.status_code == 403


def test_approve_cycle_sets_member_evaluations_approved(
    client: TestClient,
    test_db: Session,
):
    admin = _user(test_db, "phase4_approve_admin", "bcn")
    member = _member(test_db, "P4APPROVE002")
    cycle = _cycle(test_db, "P4-APPROVE", status="READY_FOR_APPROVAL")
    _member_evaluation(test_db, cycle, member, status="APPEAL_RESOLVED")

    response = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/approve",
        json={"approvalNote": "Approved"},
        headers=_auth_header(admin.id),
    )
    stored_eval = test_db.scalar(
        select(MemberEvaluation).where(MemberEvaluation.member_id == member.id)
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "APPROVED"
    assert stored_eval.status == "APPROVED"
    assert stored_eval.approved_by_user_id == admin.id


def test_lock_cycle_requires_approved_status(client: TestClient, test_db: Session):
    admin = _user(test_db, "phase4_lock_admin", "bcn")
    cycle = _cycle(test_db, "P4-LOCK-DENIED", status="READY_FOR_APPROVAL")

    response = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/lock",
        headers=_auth_header(admin.id),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "EVALUATION_INVALID_STATUS_TRANSITION"


def test_reopen_correction_allowed_only_before_lock(
    client: TestClient,
    test_db: Session,
):
    admin = _user(test_db, "phase4_reopen_admin", "bcn")
    approved_cycle = _cycle(test_db, "P4-REOPEN", status="APPROVED")
    locked_cycle = _cycle(test_db, "P4-REOPEN-LOCKED", status="LOCKED")

    allowed = client.post(
        f"/api/v2/evaluations/cycles/{approved_cycle.id}/reopen-correction",
        json={"reason": "Correction needed"},
        headers=_auth_header(admin.id),
    )
    denied = client.post(
        f"/api/v2/evaluations/cycles/{locked_cycle.id}/reopen-correction",
        json={"reason": "Nope"},
        headers=_auth_header(admin.id),
    )

    assert allowed.status_code == 200
    assert allowed.json()["data"]["status"] == "APPEAL_RESOLUTION"
    assert denied.status_code == 409
    assert denied.json()["detail"]["code"] == "EVALUATION_CORRECTION_NOT_ALLOWED"
