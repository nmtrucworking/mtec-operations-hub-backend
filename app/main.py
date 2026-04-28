import logging

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.core.config import AUTO_CREATE_TABLES, CORS_ORIGINS, ENABLE_SEED_DATA
from app.core.security import get_password_hash
from app.db import Base, get_engine, get_session_factory, ping_database
from app.models import User
from app.routers.ai import router as ai_router
from app.routers.assets import router as assets_router
from app.routers.auth import router as auth_router
from app.routers.dashboard import router as dashboard_router
from app.routers.discipline import router as discipline_router
from app.routers.members import router as members_router
from app.routers.requests import router as requests_router
from app.routers.settings import router as settings_router
from app.routers.transactions import router as transactions_router
from app.routers.users import router as users_router

logger = logging.getLogger(__name__)

app = FastAPI(title="MTEC Operations Hub Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    """
    Run initialisation tasks after the HTTP server has bound to its port.

    Critical design decision: this handler must NEVER raise an unhandled
    exception. If it does, Uvicorn will kill the worker process before
    Render's load balancer can reach /health, causing a permanent deploy
    failure. All database operations are therefore wrapped in try/except.
    """
    if AUTO_CREATE_TABLES:
        try:
            engine = get_engine()
            Base.metadata.create_all(bind=engine)
            logger.info("[startup] Database tables verified/created.")
        except Exception as exc:  # noqa: BLE001
            # Log the error and continue — the app must stay alive so that
            # /health can respond and report the degraded state.
            logger.error(
                "[startup] Could not create database tables: %s. "
                "The application will start without a database connection.",
                exc,
            )

    if ENABLE_SEED_DATA:
        try:
            _seed_users()
        except Exception as exc:  # noqa: BLE001
            logger.error("[startup] Seed data step failed: %s", exc)


def _seed_users() -> None:
    defaults = [
        ("bcn", "BCN Admin", "bcn"),
        ("bvh_hr", "BVH HR", "bvh_hr"),
        ("bvh_finance", "BVH Finance", "bvh_finance"),
        ("bvh_discipline", "BVH Discipline", "bvh_discipline"),
        ("bvh_logistics", "BVH Logistics", "bvh_logistics"),
        ("bcm", "BCM", "bcm"),
        ("member", "Member", "member"),
    ]

    factory = get_session_factory()
    db = factory()
    try:
        for username, full_name, role in defaults:
            existing = db.scalar(select(User).where(User.username == username))
            if existing:
                continue
            db.add(
                User(
                    username=username,
                    password_hash=get_password_hash("123456Abc!"),
                    full_name=full_name,
                    role=role,
                    avatar_initials="".join(part[0] for part in full_name.split()[:2]).upper(),
                    is_active=True,
                )
            )
        db.commit()
    finally:
        db.close()


@app.get("/health")
def health(response: Response) -> dict:
    """
    Readiness probe endpoint consumed by Render's health check system.

    Behaviour:
    - Calls ping_database(), which issues `SELECT 1` to the configured DB.
    - If the query succeeds within the connection timeout, returns HTTP 200
      with {"status": "ok", "database": "connected"}.
    - If the query fails for any reason (misconfiguration, network error,
      DB server down), returns HTTP 503 with a machine-readable error body.
      HTTP 503 tells Render that the service is alive but not yet ready,
      which prevents premature traffic routing without killing the deploy.
    """
    db_ok = ping_database()
    if db_ok:
        return {"status": "ok", "database": "connected"}

    response.status_code = 503
    return {"status": "degraded", "database": "unreachable"}


app.include_router(auth_router)
app.include_router(users_router)
app.include_router(members_router)
app.include_router(requests_router)
app.include_router(transactions_router)
app.include_router(dashboard_router)
app.include_router(assets_router)
app.include_router(discipline_router)
app.include_router(settings_router)
app.include_router(ai_router)
