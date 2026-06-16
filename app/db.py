"""
Database connection module.

Design principle: lazy initialization.
The SQLAlchemy engine is created on the first call to `get_engine()`.

This backend is PostgreSQL-only. `DATABASE_URL` must already be normalized
to the `postgresql+psycopg://...` form in `app.core.config`.
"""

from __future__ import annotations

import logging
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import DATABASE_URL

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def _build_engine(url: str) -> Engine:
    """Construct the singleton PostgreSQL SQLAlchemy engine."""
    return create_engine(
        url,
        poolclass=NullPool,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )


def get_engine() -> Engine:
    """Return the singleton engine, creating it on the first call."""
    global _engine, _SessionLocal

    if _engine is not None:
        return _engine

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. Configure it with a PostgreSQL connection string."
        )

    logger.info(
        "[db] Initialising database engine for URL scheme: %s",
        DATABASE_URL.split(":", 1)[0],
    )
    _engine = _build_engine(DATABASE_URL)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


def get_session_factory() -> sessionmaker:
    """Return the session factory, triggering engine creation if needed."""
    get_engine()
    assert _SessionLocal is not None  # noqa: S101
    return _SessionLocal


def ping_database() -> bool:
    """Execute a trivial query against the configured database."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (OperationalError, SQLAlchemyError, RuntimeError) as exc:
        logger.warning("[db] Health ping failed: %s", exc)
        return False


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    from fastapi import HTTPException, status

    try:
        factory = get_session_factory()
    except RuntimeError as exc:
        logger.error("[db] Cannot open session - engine not available: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured. Contact the system administrator.",
        ) from exc

    db: Session = factory()
    try:
        yield db
    finally:
        db.close()
