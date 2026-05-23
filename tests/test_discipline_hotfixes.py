from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import (
    Attendance,
    DisciplineRecord,
    Meeting,
    Member,
    User,
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


def _member(test_db: Session, mssv: str = "DISC001") -> Member:
    member = Member(mssv=mssv, name=f"Member {mssv}", ban="BCNg")
    test_db.add(member)
    test_db.commit()
    return member


def _meeting(test_db: Session) -> Meeting:
    meeting = Meeting(
        title="Discipline hotfix meeting",
        date=datetime(2026, 5, 10, tzinfo=UTC),
        meeting_type="Monthly",
        status="Completed",
    )
    test_db.add(meeting)
    test_db.commit()
    return meeting


def test_legacy_stats_excludes_khong_variants(
    client: TestClient,
    test_db: Session,
    monkeypatch,
):
    monkeypatch.setattr("app.core.config.DISCIPLINE_LEGACY_READ_ONLY", False)
    user = _user(test_db, "discipline_stats", "bcn")
    test_db.add_all(
        [
            DisciplineRecord(mssv="D001", name="No 1", discipline_level="Khong"),
            DisciplineRecord(mssv="D002", name="No 2", discipline_level="Không"),
            DisciplineRecord(mssv="D003", name="No 3", discipline_level="NONE"),
            DisciplineRecord(mssv="D004", name="Warned", discipline_level="Nhắc nhở"),
        ]
    )
    test_db.commit()

    stats = client.get(
        "/api/v1/discipline-records/stats",
        headers=_auth_header(user.id),
    )
    filtered = client.get(
        "/api/v1/discipline-records?disciplineLevel=NONE&pageSize=10",
        headers=_auth_header(user.id),
    )

    assert stats.status_code == 200
    assert stats.json()["data"]["warnedCases"] == 1
    assert filtered.status_code == 200
    assert filtered.json()["meta"]["total"] == 3


def test_legacy_create_normalizes_discipline_level(
    client: TestClient,
    test_db: Session,
    monkeypatch,
):
    monkeypatch.setattr("app.core.config.DISCIPLINE_LEGACY_READ_ONLY", False)
    user = _user(test_db, "discipline_create", "bcn")

    response = client.post(
        "/api/v1/discipline-records",
        json={
            "mssv": "D005",
            "name": "Warning",
            "absents": 3,
            "kpi": 90,
            "disciplineLevel": "Cảnh cáo Lần 1",
        },
        headers=_auth_header(user.id),
    )

    assert response.status_code == 200
    assert response.json()["data"]["disciplineLevel"] == "WARNING_1"
    assert response.json()["data"]["disciplineLevelLabel"] == "Cảnh cáo lần 1"


def test_legacy_attendance_sync_route_is_removed(
    client: TestClient,
    test_db: Session,
    monkeypatch,
):
    monkeypatch.setattr("app.core.config.DISCIPLINE_LEGACY_READ_ONLY", False)
    user = _user(test_db, "discipline_sync", "bvh_discipline")
    member = _member(test_db)
    meeting = _meeting(test_db)
    test_db.add(Attendance(meeting_id=meeting.id, member_id=member.id, status="Absent"))
    test_db.commit()

    response = client.post(
        f"/api/v1/discipline-records/sync-attendance/{meeting.id}",
        headers=_auth_header(user.id),
    )
    record = test_db.scalar(
        select(DisciplineRecord).where(DisciplineRecord.member_id == member.id)
    )

    assert response.status_code == 404
    assert record is None


def test_unrecorded_attendance_is_not_counted_as_absent(
    client: TestClient,
    test_db: Session,
):
    user = _user(test_db, "attendance_stats", "bcn")
    present_member = _member(test_db, "DISC-P")
    absent_member = _member(test_db, "DISC-A")
    unrecorded_member = _member(test_db, "DISC-U")
    meeting = _meeting(test_db)
    test_db.add_all(
        [
            Attendance(
                meeting_id=meeting.id,
                member_id=present_member.id,
                status="Present",
            ),
            Attendance(
                meeting_id=meeting.id,
                member_id=absent_member.id,
                status="Absent",
            ),
            Attendance(
                meeting_id=meeting.id,
                member_id=unrecorded_member.id,
                status="Unrecorded",
            ),
        ]
    )
    test_db.commit()

    response = client.get("/api/v1/meetings", headers=_auth_header(user.id))

    assert response.status_code == 200
    stats = response.json()["data"][0]["stats"]
    assert stats["present"] == 1
    assert stats["absent"] == 1
    assert stats["unrecorded"] == 1
