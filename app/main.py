import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import AUTO_CREATE_TABLES, CORS_ORIGINS, ENABLE_SEED_DATA
from app.db import Base, get_engine

from app.routers import api_v1_router

logger = logging.getLogger(__name__)


def _seed_users() -> None:
    """
    Hàm nạp dữ liệu người dùng mặc định vào hệ thống.
    """
    from sqlalchemy import select

    from app.core.security import get_password_hash
    from app.db import get_session_factory
    from app.models import User

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
                    avatar_initials="".join(
                        part[0] for part in full_name.split()[:2]
                    ).upper(),
                    is_active=True,
                )
            )
        db.commit()
    finally:
        db.close()


# Định nghĩa Lifespan Context Manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Quản lý vòng đời ứng dụng:
    - Logic trước 'yield' tương đương với 'startup'.
    - Logic sau 'yield' tương đương với 'shutdown'.
    """
    # --- PHẦN STARTUP ---
    if AUTO_CREATE_TABLES:
        try:
            engine = get_engine()
            # Sử dụng Base.metadata từ app.db
            Base.metadata.create_all(bind=engine)
            logger.info(
                "[lifespan] Hệ thống bảng cơ sở dữ liệu đã được xác nhận/khởi tạo."
            )
        except Exception as exc:
            logger.error("[lifespan] Lỗi khởi tạo bảng: %s", exc)

    if ENABLE_SEED_DATA:
        try:
            _seed_users()
            logger.info("[lifespan] Quá trình nạp dữ liệu mẫu hoàn tất.")
        except Exception as exc:
            logger.error("[lifespan] Lỗi nạp dữ liệu mẫu: %s", exc)

    yield  # Ứng dụng bắt đầu chạy và nhận request tại đây

    # --- PHẦN SHUTDOWN ---
    logger.info("[lifespan] Ứng dụng đang dừng và giải phóng tài nguyên.")


# Create the FastAPI application instance. This is the main entry point for the app.
app = FastAPI(title="MTEC Operations Hub Backend", version="1.2.0")


# CORS middleware is required to allow the frontend (served from a different origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=("*" not in CORS_ORIGINS),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers. The order here doesn't usually matter, but it's a good idea to keep related routes together.

app.include_router(api_v1_router, prefix="/api/v1")
app.include_router(api_v1_router, prefix="/api/v1/api")
