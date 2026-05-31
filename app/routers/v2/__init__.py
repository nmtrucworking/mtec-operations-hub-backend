from fastapi import APIRouter

from .auth import router as auth_router
from .evaluation_reports import router as evaluation_reports_router
from .evaluations import router as evaluations_router
from .evaluation_unit_permissions import router as evaluation_unit_permissions_router

api_v2_router = APIRouter()

# mount v2 routers
api_v2_router.include_router(auth_router)
api_v2_router.include_router(evaluations_router)
api_v2_router.include_router(evaluation_reports_router)
api_v2_router.include_router(evaluation_unit_permissions_router)
