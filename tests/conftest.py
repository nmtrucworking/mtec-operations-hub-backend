from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
import fakeredis

from app.db import Base, get_db
from app.main import app
from app import models  # Sử dụng cú pháp phân rã để tránh ghi đè biến 'app'

@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    fake_redis_client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("app.core.rate_limit.redis_client", fake_redis_client)
    monkeypatch.setattr("app.routers.auth.redis_client", fake_redis_client)
    yield fake_redis_client
    fake_redis_client.flushall()

@pytest.fixture
def test_db() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def client(test_db: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()