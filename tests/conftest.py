import os
from collections.abc import Generator

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app import models  # noqa: F401
from app.db import Base, get_db
from app.main import app


def _get_test_database_url() -> str:
    raw_url = os.getenv("TEST_DATABASE_URL", "").strip() or os.getenv("DATABASE_URL", "").strip()
    if not raw_url:
        pytest.fail("Set TEST_DATABASE_URL (preferred) or DATABASE_URL to a PostgreSQL test database.")

    normalized = str(make_url(raw_url))
    if not normalized.startswith("postgresql+psycopg://"):
        pytest.fail("Tests now require a PostgreSQL database URL using the psycopg driver.")

    parsed = make_url(normalized)
    database_name = (parsed.database or "").lower()
    if "test" not in database_name:
        pytest.fail(
            "Refusing to run destructive test setup against a non-test database. "
            "Use a database name containing 'test'."
        )
    return normalized


@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    fake_redis_client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("app.core.rate_limit.redis_client", fake_redis_client)
    monkeypatch.setattr("app.routers.auth.redis_client", fake_redis_client)
    yield fake_redis_client
    fake_redis_client.flushall()


@pytest.fixture
def test_db() -> Generator[Session, None, None]:
    engine = create_engine(
        _get_test_database_url(),
        poolclass=NullPool,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def client(test_db: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
