import logging
from contextlib import asynccontextmanager

from fastapi import Request
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import AUTO_CREATE_TABLES, CORS_ORIGINS, ENABLE_SEED_DATA
from app.core.response import api_response
from app.db import Base, get_engine

from app.routers import api_v1_router
from app.routers.v2 import api_v2_router

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
            import app.models  # Đảm bảo tất cả models đã được load trước khi create_all
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

    try:
        from app.services.evaluation_compute_jobs import EvaluationComputeJobService
        EvaluationComputeJobService.cleanup_stale_jobs()
        logger.info("[lifespan] Quá trình dọn dẹp các compute jobs bị gián đoạn hoàn tất.")
    except Exception as exc:
        logger.error("[lifespan] Lỗi dọn dẹp stale compute jobs: %s", exc)

    yield  # Ứng dụng bắt đầu chạy và nhận request tại đây

    # --- PHẦN SHUTDOWN ---
    logger.info("[lifespan] Ứng dụng đang dừng và giải phóng tài nguyên.")


# Create the FastAPI application instance. This is the main entry point for the app.
app = FastAPI(title="MTEC Operations Hub Backend", version="2.1.1", lifespan=lifespan)


# CORS middleware is required to allow the frontend (served from a different origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=("*" not in CORS_ORIGINS),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "[unhandled_exception] %s %s failed: %s",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=500,
        content=api_response(
            error={
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Unexpected server error",
            }
        ),
    )

# Register API routers. The order here doesn't usually matter, but it's a good idea to keep related routes together.

app.include_router(api_v1_router, prefix="/api/v1")
app.include_router(api_v2_router, prefix="/api/v2")


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}
