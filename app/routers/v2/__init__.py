from fastapi import APIRouter

from .auth import router as auth_router
from .evaluations import router as evaluations_router

api_v2_router = APIRouter()

# mount v2 routers
api_v2_router.include_router(auth_router)
api_v2_router.include_router(evaluations_router)
