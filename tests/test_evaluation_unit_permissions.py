from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import (
    User,
    Member,
    EvaluationCycle,
    EvaluationCriterion,
    MemberCycleRole,
    UserUnitPermission,
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


def _member(test_db: Session, mssv: str = "M001", *, ban: str | None = None) -> Member:
    member = Member(mssv=mssv, name=f"Member {mssv}", ban=ban)
    test_db.add(member)
    test_db.commit()
    return member


def _cycle(test_db: Session, code: str = "CYCLE-UNIT") -> EvaluationCycle:
    cycle = EvaluationCycle(
        code=code,
        name="Unit Test Cycle",
        type="MONTHLY",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
    )
    test_db.add(cycle)
    test_db.commit()
    return cycle


def _criterion(test_db: Session, code: str, *, component: str = "III_B", unit_code: str | None = None) -> EvaluationCriterion:
    c = EvaluationCriterion(
        code=code,
        name=code,
        component=component,
        unit_scope="UNIT_SPECIFIC" if unit_code else "ALL",
        unit_code=unit_code,
        max_score=10.0,
        score_method="MANUAL",
        requires_evidence=False,
    )
    test_db.add(c)
    test_db.commit()
    return c


def _grant_user_unit_permission(test_db: Session, user: User, unit_code: str, **fields) -> UserUnitPermission:
    perm = UserUnitPermission(
        user_id=user.id,
        unit_code=unit_code,
        permission_role=fields.get("permission_role", "UNIT_LEAD"),
        can_view_unit_results=fields.get("can_view_unit_results", False),
        can_score_component_ii=fields.get("can_score_component_ii", False),
        can_score_component_iii_a=fields.get("can_score_component_iii_a", False),
        can_score_component_iii_b=fields.get("can_score_component_iii_b", False),
        can_submit_evidence=fields.get("can_submit_evidence", True),
        can_verify_evidence=fields.get("can_verify_evidence", False),
        can_review_appeal=fields.get("can_review_appeal", False),
    )
    test_db.add(perm)
    test_db.commit()
    return perm


def _assign_member_role(test_db: Session, cycle: EvaluationCycle, member: Member, unit_code: str):
    r = MemberCycleRole(cycle_id=cycle.id, member_id=member.id, unit_code=unit_code, role_type="MEMBER", participation_weight=1.0)
    test_db.add(r)
    test_db.commit()
    return r


def test_bcm_can_only_view_members_in_own_unit(client: TestClient, test_db: Session):
    bcm = _user(test_db, "bcm_unit", "bcm")
    cycle = _cycle(test_db, "CYCLE-VIEW-1")
    member = _member(test_db, "MV001")
    _assign_member_role(test_db, cycle, member, "BCNg")
    _grant_user_unit_permission(test_db, bcm, "BCNg", can_view_unit_results=True)

    resp = client.get(f"/api/v2/evaluations/cycles/{cycle.id}/members/{member.id}", headers=_auth_header(bcm.id))
    assert resp.status_code == 200


def test_bcm_cannot_view_other_unit_member_result(client: TestClient, test_db: Session):
    bcm = _user(test_db, "bcm_other", "bcm")
    cycle = _cycle(test_db, "CYCLE-VIEW-2")
    member = _member(test_db, "MV002")
    _assign_member_role(test_db, cycle, member, "BTT")
    _grant_user_unit_permission(test_db, bcm, "BCNg", can_view_unit_results=True)

    resp = client.get(f"/api/v2/evaluations/cycles/{cycle.id}/members/{member.id}", headers=_auth_header(bcm.id))
    assert resp.status_code == 403


def test_bcm_can_score_iii_b_only_for_own_unit(client: TestClient, test_db: Session):
    bcm = _user(test_db, "bcm_score", "bcm")
    cycle = _cycle(test_db, "CYCLE-SCORE-1")
    member = _member(test_db, "MV003")
    _assign_member_role(test_db, cycle, member, "BCNg")
    criterion = _criterion(test_db, "III-B.BCNg.01", component="III_B", unit_code="BCNg")
    _grant_user_unit_permission(test_db, bcm, "BCNg", can_score_component_iii_b=True)

    resp = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/score-events",
        json={
            "memberId": member.id,
            "criterionId": criterion.id,
            "criterionCode": criterion.code,
            "eventType": "MANUAL",
            "scoreDelta": 5,
        },
        headers=_auth_header(bcm.id),
    )
    assert resp.status_code == 200


def test_bcm_cannot_score_component_i(client: TestClient, test_db: Session):
    bcm = _user(test_db, "bcm_score_denied", "bcm")
    cycle = _cycle(test_db, "CYCLE-SCORE-2")
    member = _member(test_db, "MV004")
    _assign_member_role(test_db, cycle, member, "BCNg")
    criterion = _criterion(test_db, "I.XX", component="I")
    _grant_user_unit_permission(test_db, bcm, "BCNg", can_score_component_iii_b=True)

    resp = client.post(
        f"/api/v2/evaluations/cycles/{cycle.id}/score-events",
        json={
            "memberId": member.id,
            "criterionId": criterion.id,
            "criterionCode": criterion.code,
            "eventType": "MANUAL",
            "scoreDelta": 3,
        },
        headers=_auth_header(bcm.id),
    )
    assert resp.status_code == 403
