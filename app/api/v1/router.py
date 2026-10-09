from fastapi import APIRouter

from app.api.v1.chat import router as chat_router
from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router
from app.api.v1.readiness import router as readiness_router
from app.api.v1.admin import router as admin_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.document_lifecycle import router as lifecycle_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(readiness_router)
api_router.include_router(documents_router)
api_router.include_router(chat_router)
api_router.include_router(admin_router)
api_router.include_router(jobs_router)
api_router.include_router(lifecycle_router)
