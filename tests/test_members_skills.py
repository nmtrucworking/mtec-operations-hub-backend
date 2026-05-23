from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import pytest

from app.models import User, Member
from app.db import get_db


@pytest.fixture
def auth_user(test_db: Session):
    # create a test user with bvh_hr role
    user = User(username="22000001", password_hash="x", full_name="Test User", role="bvh_hr", is_active=True)
    test_db.add(user)
    test_db.flush()
    return user


def override_get_current_user(user: User):
    def _dep():
        return user
    return _dep


def test_create_update_member_skills(client: TestClient, test_db: Session, auth_user: User, monkeypatch):
    # override current user dependency
    from app.deps import get_current_user

    monkeypatch.setattr('app.deps.get_current_user', lambda: auth_user)
    # also ensure the app dependency override for get_db is respected (conftest provides it)

    payload = {
        "mssv": "22000001",
        "name": "Nguyen Van Test",
        "ban": "Ban A",
        "roleTitle": "Thanh vien",
        "hardSkills": [{"name": "React", "level": "Tốt"}],
        "softSkills": [{"name": "Teamwork", "level": "Trung bình"}]
    }

    res = client.post('/api/v1/members', json=payload)
    assert res.status_code >= 200 and res.status_code < 300, res.text
    data = res.json().get('data')
    assert data is not None
    assert data.get('hardSkills') and data.get('hardSkills')[0]['name'] == 'React'
    assert data.get('softSkills') and data.get('softSkills')[0]['name'] == 'Teamwork'

    member_id = data.get('id')

    # update skills
    patch = {
        "hardSkills": [{"name": "Vue", "level": "Cơ bản"}],
        "softSkills": []
    }
    res2 = client.patch(f'/api/v1/members/{member_id}', json=patch)
    assert res2.status_code >= 200 and res2.status_code < 300, res2.text
    data2 = res2.json().get('data')
    assert data2 is not None
    assert len(data2.get('hardSkills', [])) == 1 and data2['hardSkills'][0]['name'] == 'Vue'
    assert data2.get('softSkills', []) == []

    # test /me resolves by username
    res3 = client.get('/api/v1/members/me')
    assert res3.status_code >= 200 and res3.status_code < 300, res3.text
    data3 = res3.json().get('data')
    assert data3 is not None
    assert data3.get('mssv') == '22000001'
    assert data3.get('hardSkills')[0]['name'] == 'Vue'
*** End Patch