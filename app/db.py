"""
Database connection module.

Design principle: Lazy initialization.
The SQLAlchemy engine is NOT created at module-import time.
It is created on the first call to `get_engine()`.

Rationale: On Render, DATABASE_URL is injected via environment variable
with `sync: false`, meaning it may not be present when the Python process
first imports this module. Creating the engine eagerly (at module level)
would cause create_engine() to raise an exception that propagates through
FastAPI's import chain, killing the process before the HTTP server binds
to its port and before /health can respond to Render's health check.

By deferring engine creation to the first actual database request, the HTTP
server starts successfully regardless of DB availability. Endpoints that
require a DB session will receive an HTTP 503 error instead of silently
crashing the whole process.
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

# Module-level sentinel — None until the first call to get_engine().
_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def _build_engine(url: str) -> Engine:
    """
    Construct a SQLAlchemy Engine from the given connection URL.

    This function contains the branching logic for SQLite vs. PostgreSQL
    connection parameters. It is a pure factory — it has no side effects
    beyond creating the engine object. The actual network connection is
    established only when a session executes its first SQL statement.
    """
    if url.startswith("sqlite"):
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )
    # PostgreSQL / Supabase path
    return create_engine(
        url,
        poolclass=NullPool,
        connect_args={"connect_timeout": 10},
    )


def get_engine() -> Engine:
    """
    Return the singleton Engine, creating it on the first call.

    Thread-safety note: In a single-process Uvicorn deployment (workers=1)
    or with Gunicorn pre-fork workers, each worker process initialises its
    own engine independently, so no lock is required. If you switch to a
    threading model, wrap the initialisation block in a threading.Lock.

    Raises:
        RuntimeError: If DATABASE_URL is empty/None (i.e. the environment
            variable was never set). The caller is responsible for catching
            this and returning an appropriate HTTP error.
    """
    global _engine, _SessionLocal

    if _engine is not None:
        return _engine

    url = DATABASE_URL
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Configure it in the Render dashboard under Environment → DATABASE_URL."
        )

    logger.info(
        "[db] Initialising database engine for URL scheme: %s", url.split(":")[0]
    )
    _engine = _build_engine(url)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


def get_session_factory() -> sessionmaker:
    """Return the sessionmaker, triggering engine creation if necessary."""
    get_engine()  # ensures _SessionLocal is populated
    assert _SessionLocal is not None  # noqa: S101  # guaranteed by get_engine()
    return _SessionLocal


def ping_database() -> bool:
    """
    Execute `SELECT 1` against the configured database.

    Returns True if the round-trip succeeds, False otherwise.
    Does NOT raise — all exceptions are caught and logged so that the
    /health endpoint can translate the result into an HTTP status code
    without crashing the server.
    """
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
    """
    FastAPI dependency that yields a database session.

    If the engine cannot be initialised (e.g. DATABASE_URL is missing),
    this raises HTTP 503 so that individual endpoints fail gracefully
    instead of propagating an unhandled RuntimeError.
    """
    from fastapi import HTTPException, status  # local import to avoid circular deps

    try:
        factory = get_session_factory()
    except RuntimeError as exc:
        logger.error("[db] Cannot open session — engine not available: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured. Contact the system administrator.",
        ) from exc

    db: Session = factory()
    try:
        yield db
    finally:
        db.close()
