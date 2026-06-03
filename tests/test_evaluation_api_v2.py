from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import (
    EvaluationCriterion,
    EvaluationCycle,
    EvaluationEvidence,
    EvaluationScoreEvent,
    Member,
    MemberCycleRole,
    MemberEvaluation,
    MemberEvaluationBreakdown,
    User,
)
from app.services.evaluation_criteria_seed import DEFAULT_EVALUATION_CRITERIA_2026


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


def _member(test_db: Session, mssv: str = "MTEC001", *, ban: str | None = None) -> Member:
    member = Member(mssv=mssv, name=f"Member {mssv}", ban=ban)
    test_db.add(member)
    test_db.commit()
    return member


def _cycle(test_db: Session, code: str = "2026-05-API") -> EvaluationCycle:
    cycle = EvaluationCycle(
        code=code,
        name="API cycle",
        type="MONTHLY",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
    )
    test_db.add(cycle)
    test_db.commit()
    return cycle


def _criterion(
    test_db: Session,
    code: str = "I.1",
    *,
    component: str = "I",
    unit_code: str | None = None,
    requires_evidence: bool = False,
    max_score: float = 10.0,
) -> EvaluationCriterion:
    criterion = EvaluationCriterion(
        code=code,
        name=code,
        component=component,
        unit_scope="UNIT_SPECIFIC" if unit_code else "ALL",
        unit_code=unit_code,
        max_score=max_score,
        score_method="MANUAL",
        requires_evidence=requires_evidence,
    )
    test_db.add(criterion)
    test_db.commit()
    return criterion


def _score_event(
    test_db: Session,
    cycle: EvaluationCycle,
    member: Member,
    criterion: EvaluationCriterion,
    score_delta: float = 8.0,
) -> EvaluationScoreEvent:
    event = EvaluationScoreEvent(
        cycle_id=cycle.id,
        member_id=member.id,
        criterion_id=criterion.id,
        criterion_code=criterion.code,
        component=criterion.component,
        unit_code=criterion.unit_code,
        event_type="MANUAL_SCORE",
        score_delta=score_delta,
    )
    test_db.add(event)
    test_db.commit()
    return event


def test_create_cycle_requires_operator_role(client: TestClient, test_db: Session):
    user = _user(test_db, "plain_member", "member")

    response = client.post(
        "/api/v2/evaluations/cycles",
        json={
            "code": "2026-05-MEMBER",
            "name": "Member attempt",
            "type": "MONTHLY",
            "startDate": "2026-05-01",
            "endDate": "2026-05-31",
        },
        headers=_auth_header(user.id),
    )

    assert response.status_code == 403


def test_create_cycle_success(client: TestClient, test_db: Session):
    user = _user(test_db, "operator", "bvh_discipline")

    response = client.post(
        "/api/v2/evaluations/cycles",
        json={
            "code": "2026-05-MONTHLY",
            "name": "May evaluation",
            "type": "MONTHLY",
            "startDate": "2026-05-01",
            "endDate": "2026-05-31",
        },
        headers=_auth_header(user.id),
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["code"] == "2026-05-MONTHLY"
    assert data["status"] == "DRAFT"


def test_create_cycle_rejects_invalid_date_range(client: TestClient, test_db: Session):
    user = _user(test_db, "operator_date", "bvh_discipline")

    response = client.post(
        "/api/v2/evaluations/cycles",
        json={
            "code": "2026-05-BAD-DATE",
            "name": "Bad date",
            "type": "MONTHLY",
            "startDate": "2026-05-31",
            "endDate": "2026-05-01",
        },
        headers=_auth_header(user.id),
    )

    assert response.status_code == 422


def test_create_cycle_rejects_duplicate_code(client: TestClient, test_db: Session):
    user = _user(test_db, "operator_dup", "bvh_hr")
    _cycle(test_db, "2026-05-DUP")

    response = client.post(
        "/api/v2/evaluations/cycles",
        json={
            "code": "2026-05-DUP",
            "name": "Duplicate",
            "type": "MONTHLY",
            "startDate": "2026-05-01",
            "endDate": "2026-05-31",
        },
        headers=_auth_header(user.id),
    )

    assert response.status_code == 409


def test_lock_cycle_requires_bcn(client: TestClient, test_db: Session):
    operator = _user(test_db, "operator_lock", "bvh_discipline")
    admin = _user(test_db, "admin_lock", "bcn")
    cycle = _cycle(test_db, "2026-05-LOCK")
    cycle.status = "APPROVED"
    test_db.commit()

    denied = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/lock",
        headers=_auth_header(operator.id),
    )
    allowed = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/lock",
        headers=_auth_header(admin.id),
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["data"]["status"] == "LOCKED"


def test_seed_criteria_is_idempotent(client: TestClient, test_db: Session):
    admin = _user(test_db, "criteria_admin", "bcn")

    first = client.post(
        "/api/v2/evaluations/criteria/seed",
        json={"version": "2026"},
        headers=_auth_header(admin.id),
    )
    second = client.post(
        "/api/v2/evaluations/criteria/seed",
        json={"version": "2026"},
        headers=_auth_header(admin.id),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["insertedCount"] == len(
        DEFAULT_EVALUATION_CRITERIA_2026
    )
    assert second.json()["data"]["insertedCount"] == 0
    assert second.json()["data"]["updatedCount"] == len(
        DEFAULT_EVALUATION_CRITERIA_2026
    )


def test_create_criterion_requires_admin_or_discipline(client: TestClient, test_db: Session):
    user = _user(test_db, "criteria_member", "member")

    response = client.post(
        "/api/v2/evaluations/criteria",
        json={
            "code": "CUSTOM.1",
            "name": "Custom criterion",
            "component": "I",
            "maxScore": 10,
            "scoreMethod": "MANUAL",
        },
        headers=_auth_header(user.id),
    )

    assert response.status_code == 403


def test_list_criteria_filters_by_component(client: TestClient, test_db: Session):
    user = _user(test_db, "criteria_viewer", "member")
    _criterion(test_db, "I.1", component="I")
    _criterion(test_db, "II.1", component="II")

    response = client.get(
        "/api/v2/evaluations/criteria?component=II",
        headers=_auth_header(user.id),
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["component"] == "II"


def test_create_score_event_requires_recorder_role(client: TestClient, test_db: Session):
    user = _user(test_db, "score_member", "member")
    cycle = _cycle(test_db, "2026-05-SCORE-DENIED")
    member = _member(test_db, "SCORE001")
    criterion = _criterion(test_db, "I.2")

    response = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/score-events",
        json={
            "memberId": member.id,
            "criterionId": criterion.id,
            "criterionCode": criterion.code,
            "eventType": "BASE",
            "scoreDelta": 5,
        },
        headers=_auth_header(user.id),
    )

    assert response.status_code == 403


def test_create_score_event_success(client: TestClient, test_db: Session):
    recorder = _user(test_db, "score_recorder", "bvh_discipline")
    cycle = _cycle(test_db, "2026-05-SCORE")
    member = _member(test_db, "SCORE002")
    criterion = _criterion(test_db, "I.3")

    response = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/score-events",
        json={
            "memberId": member.id,
            "criterionId": criterion.id,
            "criterionCode": criterion.code,
            "eventType": "PENALTY",
            "sourceType": "MANUAL",
            "sourceId": "manual-1",
            "scoreDelta": 2,
        },
        headers=_auth_header(recorder.id),
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["criterionCode"] == "I.3"
    assert data["scoreDelta"] == -2


def test_create_score_event_rejects_locked_cycle(client: TestClient, test_db: Session):
    recorder = _user(test_db, "score_locked", "bvh_discipline")
    cycle = _cycle(test_db, "2026-05-SCORE-LOCKED")
    cycle.status = "LOCKED"
    member = _member(test_db, "SCORE003")
    criterion = _criterion(test_db, "I.4")
    test_db.commit()

    response = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/score-events",
        json={
            "memberId": member.id,
            "criterionId": criterion.id,
            "criterionCode": criterion.code,
            "eventType": "BASE",
            "scoreDelta": 2,
        },
        headers=_auth_header(recorder.id),
    )

    assert response.status_code == 409


def test_create_evidence_for_own_member(client: TestClient, test_db: Session):
    member = _member(test_db, "OWNER001")
    owner = _user(test_db, "OWNER001", "member")
    cycle = _cycle(test_db, "2026-05-EVIDENCE")
    criterion = _criterion(test_db, "I.5")
    event = _score_event(test_db, cycle, member, criterion)

    response = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/evidence",
        json={
            "memberId": member.id,
            "scoreEventId": event.id,
            "evidenceType": "LINK",
            "title": "Proof",
            "url": "https://example.test/proof",
        },
        headers=_auth_header(owner.id),
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "PENDING"


def test_evidence_response_filters_sensitive_metadata(client: TestClient, test_db: Session):
    member = _member(test_db, "META001")
    owner = _user(test_db, "META001", "member")
    cycle = _cycle(test_db, "2026-05-EVIDENCE-META")

    response = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/evidence",
        json={
            "memberId": member.id,
            "evidenceType": "LINK",
            "title": "Proof",
            "url": "https://example.test/proof",
            "metadata": {
                "displayName": "public",
                "accessToken": "secret-token",
                "nested": {"signed_url": "https://internal.test/signed"},
            },
        },
        headers=_auth_header(owner.id),
    )

    assert response.status_code == 200
    assert response.json()["data"]["metadata"] == {
        "displayName": "public",
        "nested": {},
    }


def test_verify_evidence_requires_manager_role(client: TestClient, test_db: Session):
    member = _member(test_db, "VERIFY001")
    owner = _user(test_db, "VERIFY001", "member")
    manager = _user(test_db, "verify_manager", "bvh_hr")
    cycle = _cycle(test_db, "2026-05-VERIFY")
    evidence = EvaluationEvidence(
        cycle_id=cycle.id,
        member_id=member.id,
        evidence_type="LINK",
        title="Proof",
        url="https://example.test/proof",
    )
    test_db.add(evidence)
    test_db.commit()

    denied = client.patch(
        f"/api/v2/evaluations/evidence/{evidence.id}/verify",
        json={},
        headers=_auth_header(owner.id),
    )
    allowed = client.patch(
        f"/api/v2/evaluations/evidence/{evidence.id}/verify",
        json={},
        headers=_auth_header(manager.id),
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["data"]["status"] == "VERIFIED"


def test_verify_evidence_rejects_self_review(client: TestClient, test_db: Session):
    member = _member(test_db, "SELFVERIFY001")
    reviewer = _user(test_db, "self_review_manager", "bvh_hr")
    cycle = _cycle(test_db, "2026-05-SELFVERIFY")
    evidence = EvaluationEvidence(
        cycle_id=cycle.id,
        member_id=member.id,
        evidence_type="LINK",
        title="Proof",
        url="https://example.test/proof",
        submitted_by_user_id=reviewer.id,
    )
    test_db.add(evidence)
    test_db.commit()

    response = client.patch(
        f"/api/v2/evaluations/evidence/{evidence.id}/verify",
        json={},
        headers=_auth_header(reviewer.id),
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "EVIDENCE_SELF_REVIEW_NOT_ALLOWED"


def test_void_score_event_does_not_delete_event(client: TestClient, test_db: Session):
    manager = _user(test_db, "void_manager", "bvh_discipline")
    cycle = _cycle(test_db, "2026-05-VOID")
    member = _member(test_db, "VOID001")
    criterion = _criterion(test_db, "I.6")
    event = _score_event(test_db, cycle, member, criterion)

    response = client.patch(
        f"/api/v2/evaluations/score-events/{event.id}/void",
        json={"reason": "Duplicate"},
        headers=_auth_header(manager.id),
    )
    stored = test_db.get(EvaluationScoreEvent, event.id)

    assert response.status_code == 200
    assert stored is not None
    assert stored.is_void is True
    assert response.json()["data"]["isVoid"] is True


def test_compute_cycle_success(client: TestClient, test_db: Session):
    manager = _user(test_db, "compute_manager", "bvh_discipline")
    cycle = _cycle(test_db, "2026-05-COMPUTE")
    member = _member(test_db, "COMPUTE001", ban="BCNg")
    criterion = _criterion(test_db, "III-B.BCNg.01", component="III_B", unit_code="BCNg", max_score=20)
    _score_event(test_db, cycle, member, criterion, score_delta=18)

    response = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/compute",
        json={"strict": True, "evidenceMode": "draft"},
        headers=_auth_header(manager.id),
    )
    stored = test_db.scalar(
        select(MemberEvaluation).where(MemberEvaluation.member_id == member.id)
    )

    assert response.status_code == 200
    assert response.json()["data"]["computedMembers"] == 1
    assert stored is not None
    assert stored.component_iii_b_score == 18


def test_compute_cycle_includes_active_members_without_roles_or_events(
    client: TestClient, test_db: Session
):
    manager = _user(test_db, "compute_active", "bvh_discipline")
    cycle = _cycle(test_db, "2026-05-ACTIVE")
    member = _member(test_db, "ACTIVE001")
    _criterion(test_db, "I.9", component="I", max_score=10)

    response = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/compute",
        json={"strict": False, "evidenceMode": "draft"},
        headers=_auth_header(manager.id),
    )
    stored = test_db.scalar(
        select(MemberEvaluation).where(MemberEvaluation.member_id == member.id)
    )

    assert response.status_code == 200
    assert response.json()["data"]["computedMembers"] == 1
    assert stored is not None
    assert stored.total_score == 0


def test_compute_cycle_requires_operator_role(client: TestClient, test_db: Session):
    user = _user(test_db, "compute_member", "member")
    cycle = _cycle(test_db, "2026-05-COMPUTE-DENIED")

    response = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/compute",
        json={"strict": True, "evidenceMode": "draft"},
        headers=_auth_header(user.id),
    )

    assert response.status_code == 403


def test_cycle_summary_counts_active_members(client: TestClient, test_db: Session):
    manager = _user(test_db, "summary_manager", "bvh_discipline")
    cycle = _cycle(test_db, "2026-05-SUMMARY")
    _member(test_db, "SUMMARY001")
    _member(test_db, "SUMMARY002", ban="BCNg")

    response = client.get(
        f"/api/v2/evaluations/cycles/{cycle.id}/summary",
        headers=_auth_header(manager.id),
    )

    assert response.status_code == 200
    assert response.json()["data"]["totalMembers"] == 2


def test_compute_cycle_maps_weight_error_to_422(client: TestClient, test_db: Session):
    manager = _user(test_db, "compute_weight", "bvh_discipline")
    cycle = _cycle(test_db, "2026-05-WEIGHT")
    member = _member(test_db, "WEIGHT001")
    criterion = _criterion(test_db, "III-B.BCNg.02", component="III_B", unit_code="BCNg", max_score=20)
    _score_event(test_db, cycle, member, criterion, score_delta=18)
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
            ),
        ]
    )
    test_db.commit()

    response = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/compute",
        json={"strict": True, "evidenceMode": "draft"},
        headers=_auth_header(manager.id),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "EVALUATION_WEIGHT_ERROR"


def test_get_member_result_allows_owner(client: TestClient, test_db: Session):
    member = _member(test_db, "RESULT001", ban="BCNg")
    owner = _user(test_db, "RESULT001", "member")
    manager = _user(test_db, "result_manager", "bvh_discipline")
    cycle = _cycle(test_db, "2026-05-RESULT")
    criterion = _criterion(test_db, "III-B.BCNg.03", component="III_B", unit_code="BCNg", max_score=20)
    _score_event(test_db, cycle, member, criterion, score_delta=12)
    client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/compute",
        json={"strict": True, "evidenceMode": "draft"},
        headers=_auth_header(manager.id),
    )

    response = client.get(
        f"/api/v2/evaluations/cycles/{cycle.id}/members/{member.id}",
        headers=_auth_header(owner.id),
    )

    assert response.status_code == 200
    assert response.json()["data"]["memberId"] == member.id


def test_get_member_result_denies_other_member(client: TestClient, test_db: Session):
    owner = _user(test_db, "OWNER002", "member")
    other_member = _member(test_db, "OTHER002")
    cycle = _cycle(test_db, "2026-05-DENY")

    response = client.get(
        f"/api/v2/evaluations/cycles/{cycle.id}/members/{other_member.id}",
        headers=_auth_header(owner.id),
    )

    assert response.status_code == 403


def test_get_cycle_members_requires_manager(client: TestClient, test_db: Session):
    user = _user(test_db, "list_member", "member")
    cycle = _cycle(test_db, "2026-05-LIST")

    response = client.get(
        f"/api/v2/evaluations/cycles/{cycle.id}/members",
        headers=_auth_header(user.id),
    )

    assert response.status_code == 403


def test_member_roles_bulk_can_update_existing_primary_role(
    client: TestClient,
    test_db: Session,
):
    manager = _user(test_db, "bulk_roles_manager", "bvh_hr")
    cycle = _cycle(test_db, "2026-05-BULK-ROLES")
    member = _member(test_db, "BULKROLE001")
    payload = {
        "roles": [
            {
                "memberId": member.id,
                "unitCode": "BCNg",
                "roleType": "MEMBER",
                "roleTitle": "Thanh vien",
                "participationWeight": 1,
                "isPrimary": True,
            }
        ]
    }

    first = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/member-roles/bulk",
        json=payload,
        headers=_auth_header(manager.id),
    )
    payload["roles"][0]["roleType"] = "LEAD"
    payload["roles"][0]["roleTitle"] = "Truong nhom"
    second = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/member-roles/bulk",
        json=payload,
        headers=_auth_header(manager.id),
    )
    roles = test_db.scalars(
        select(MemberCycleRole).where(
            MemberCycleRole.cycle_id == cycle.id,
            MemberCycleRole.member_id == member.id,
        )
    ).all()

    assert first.status_code == 200
    assert first.json()["data"]["createdCount"] == 1
    assert second.status_code == 200
    assert second.json()["data"]["updatedCount"] == 1
    assert second.json()["data"]["message"]
    assert len(roles) == 1
    assert roles[0].role_type == "LEAD"
    assert roles[0].is_primary is True


def test_quick_review_cycle_returns_preview_without_persisting(
    client: TestClient,
    test_db: Session,
):
    manager = _user(test_db, "quick_manager", "bvh_discipline")
    cycle = _cycle(test_db, "2026-05-QUICK")
    member = _member(test_db, "QUICK001")
    criterion = _criterion(test_db, "I.QUICK", component="I", max_score=10)
    _score_event(test_db, cycle, member, criterion, score_delta=8)

    response = client.get(
        f"/api/v2/evaluations/cycles/{cycle.id}/quick-review",
        headers=_auth_header(manager.id),
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["cycleId"] == cycle.id
    assert data["totalMembers"] == 1
    assert data["averageScore"] == 8
    assert data["isTemporary"] is True
    assert data["persisted"] is False
    assert data["items"][0]["totalScore"] == 8
    assert test_db.scalar(select(MemberEvaluation).where(MemberEvaluation.cycle_id == cycle.id)) is None
    assert test_db.scalar(
        select(MemberEvaluationBreakdown).where(MemberEvaluationBreakdown.cycle_id == cycle.id)
    ) is None


def test_quick_review_cycle_requires_manager(client: TestClient, test_db: Session):
    user = _user(test_db, "quick_member", "member")
    cycle = _cycle(test_db, "2026-05-QUICK-DENY")

    response = client.get(
        f"/api/v2/evaluations/cycles/{cycle.id}/quick-review",
        headers=_auth_header(user.id),
    )

    assert response.status_code == 403


def test_quick_review_member_allows_owner_without_persisting(
    client: TestClient,
    test_db: Session,
):
    member = _member(test_db, "QUICK002")
    owner = _user(test_db, "QUICK002", "member")
    cycle = _cycle(test_db, "2026-05-QUICK-MEMBER")
    criterion = _criterion(test_db, "I.QUICK.2", component="I", max_score=10)
    _score_event(test_db, cycle, member, criterion, score_delta=7)

    response = client.get(
        f"/api/v2/evaluations/cycles/{cycle.id}/members/{member.id}/quick-review",
        headers=_auth_header(owner.id),
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["memberId"] == member.id
    assert data["totalScore"] == 7
    assert test_db.scalar(select(MemberEvaluation).where(MemberEvaluation.cycle_id == cycle.id)) is None


def test_quick_review_member_denies_other_member(
    client: TestClient,
    test_db: Session,
):
    owner = _user(test_db, "QUICK003", "member")
    other_member = _member(test_db, "QUICK004")
    cycle = _cycle(test_db, "2026-05-QUICK-OTHER")

    response = client.get(
        f"/api/v2/evaluations/cycles/{cycle.id}/members/{other_member.id}/quick-review",
        headers=_auth_header(owner.id),
    )

    assert response.status_code == 403


def test_create_appeal_rejects_locked_cycle(client: TestClient, test_db: Session):
    member = _member(test_db, "APPEAL001")
    owner = _user(test_db, "APPEAL001", "member")
    cycle = _cycle(test_db, "2026-05-APPEAL")
    cycle.status = "LOCKED"
    test_db.commit()

    response = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/appeals",
        json={
            "memberId": member.id,
            "appealType": "SCORE_REVIEW",
            "content": "Please review this score.",
        },
        headers=_auth_header(owner.id),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "EVALUATION_CYCLE_LOCKED"


def test_list_criteria_filters_by_cycle(client: TestClient, test_db: Session):
    user = _user(test_db, "criteria_cycle_viewer", "member")
    cycle = _cycle(test_db, "2026-05-CRIT-FILTER")
    
    crit_ok = EvaluationCriterion(
        code="I.CRIT-OK",
        name="OK",
        component="I",
        unit_scope="ALL",
        max_score=10.0,
        score_method="MANUAL",
        effective_from=date(2026, 5, 15),
        effective_to=date(2026, 5, 20),
    )
    crit_bad = EvaluationCriterion(
        code="I.CRIT-BAD",
        name="BAD",
        component="I",
        unit_scope="ALL",
        max_score=10.0,
        score_method="MANUAL",
        effective_from=date(2026, 6, 1),
    )
    test_db.add_all([crit_ok, crit_bad])
    test_db.commit()

    response = client.get(
        f"/api/v2/evaluations/criteria?cycleId={cycle.id}",
        headers=_auth_header(user.id),
    )

    assert response.status_code == 200
    data = response.json()["data"]
    codes = [item["code"] for item in data]
    assert "I.CRIT-OK" in codes
    assert "I.CRIT-BAD" not in codes
