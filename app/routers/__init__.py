from fastapi import APIRouter
from app.routers.auth import router as auth_router
from app.routers.users import router as users_router
from app.routers.members import router as members_router
from app.routers.requests import router as requests_router
from app.routers.transactions import router as transactions_router
from app.routers.dashboard import router as dashboard_router
from app.routers.assets import router as assets_router
from app.routers.discipline import router as discipline_router
from app.routers.settings import router as settings_router
from app.routers.ai import router as ai_router
from app.routers.logs import router as logs_router

api_v1_router = APIRouter()

api_v1_router.include_router(auth_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(members_router)
api_v1_router.include_router(requests_router)
api_v1_router.include_router(transactions_router)
api_v1_router.include_router(dashboard_router)
api_v1_router.include_router(assets_router)
api_v1_router.include_router(discipline_router)
api_v1_router.include_router(settings_router)
api_v1_router.include_router(ai_router)
api_v1_router.include_router(logs_router)
