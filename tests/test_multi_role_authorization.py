from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Role, Transaction, User, UserRole


def _auth_header(user_id: str) -> dict[str, str]:
    token = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


def test_pending_transactions_accepts_finance_role_from_user_roles(
    client: TestClient, test_db: Session
):
    user = User(
        id="user-multi-role-1",
        username="multi_finance",
        password_hash="hashed",
        full_name="Multi Finance",
        role="member",
        is_active=True,
    )
    role_member = Role(id="role-member", name="member")
    role_finance = Role(id="role-finance", name="bvh_finance")

    test_db.add_all([user, role_member, role_finance])
    test_db.flush()
    test_db.add_all(
        [
            UserRole(user_id=user.id, role_id=role_member.id),
            UserRole(user_id=user.id, role_id=role_finance.id),
        ]
    )

    tx = Transaction(
        date=date(2026, 5, 13),
        title="Need approval",
        type="Chi",
        amount=100_000,
        owner="Ops Team",
        category="Vat tu",
        status="Cho duyet",
        required_approval_role="bvh_finance",
        created_by_user_id=user.id,
    )
    test_db.add(tx)
    test_db.commit()

    response = client.get(
        "/api/v1/transactions/pending", headers=_auth_header(user.id)
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert len(payload) == 1
    assert payload[0]["requiredApprovalRole"] == "bvh_finance"


def test_profile_returns_roles_and_primary_role(client: TestClient, test_db: Session):
    user = User(
        id="user-multi-role-2",
        username="multi_admin",
        password_hash="hashed",
        full_name="Multi Admin",
        role="member",
        is_active=True,
    )
    role_member = Role(id="role-member-2", name="member")
    role_bcn = Role(id="role-bcn-2", name="bcn")

    test_db.add_all([user, role_member, role_bcn])
    test_db.flush()
    test_db.add_all(
        [
            UserRole(user_id=user.id, role_id=role_member.id),
            UserRole(user_id=user.id, role_id=role_bcn.id),
        ]
    )
    test_db.commit()

    response = client.get("/api/v1/settings/profile", headers=_auth_header(user.id))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["role"] == "bcn"
    assert set(data["roles"]) == {"member", "bcn"}
