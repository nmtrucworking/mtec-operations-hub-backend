from collections.abc import Generator

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool  # Bổ sung module này

from app import models  # noqa: F401 (Dùng cho side-effect đăng ký metadata)
from app.db import Base, get_db
from app.main import app


@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    fake_redis_client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("app.core.rate_limit.redis_client", fake_redis_client)
    monkeypatch.setattr("app.routers.auth.redis_client", fake_redis_client)
    yield fake_redis_client
    fake_redis_client.flushall()


@pytest.fixture
def test_db() -> Generator[Session, None, None]:
    # Thiết lập poolclass=StaticPool để dùng chung bộ nhớ giữa các thread
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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
