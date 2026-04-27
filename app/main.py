from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.core.security import get_password_hash
from app.db import Base, SessionLocal, engine
from app.models import User
from app.routers.auth import router as auth_router
from app.routers.dashboard import router as dashboard_router
from app.routers.members import router as members_router
from app.routers.requests import router as requests_router
from app.routers.transactions import router as transactions_router
from app.routers.users import router as users_router

app = FastAPI(title="MTEC Operations Hub Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    _seed_users()


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

    db = SessionLocal()
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
def health() -> dict:
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(users_router)
app.include_router(members_router)
app.include_router(requests_router)
app.include_router(transactions_router)
app.include_router(dashboard_router)
