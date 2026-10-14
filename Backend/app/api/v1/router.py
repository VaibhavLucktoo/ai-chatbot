from fastapi import APIRouter

from app.api.v1.chat import router as chat_router
from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router
from app.api.v1.readiness import router as readiness_router
from app.api.v1.admin import router as admin_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.document_lifecycle import router as lifecycle_router
from app.api.v1.document_catalog import router as catalog_router
from app.api.v1.metrics import router as metrics_router
from app.api.v1.assistants import router as assistants_router, admin_router as assistant_admin_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(readiness_router)
api_router.include_router(documents_router)
api_router.include_router(chat_router)
api_router.include_router(admin_router)
api_router.include_router(jobs_router)
api_router.include_router(lifecycle_router)
api_router.include_router(catalog_router)
api_router.include_router(metrics_router)
api_router.include_router(assistants_router)
api_router.include_router(assistant_admin_router)
