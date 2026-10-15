from pathlib import Path
import secrets

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.middleware import LocalWorkspaceMiddleware
from app.core.lifespan import lifespan
from app.core.production_access import ProductionAccessMiddleware, validate_production
from app.api.v1.widget_assets import page_router as widget_page_router

ADMIN_DIRECTORY = Path(__file__).parent / "admin"


def create_app() -> FastAPI:
    settings = get_settings()
    production = settings.app_env == "production"
    origin = validate_production(settings) if production else ""

    application = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )
    application.include_router(api_router, prefix="/v1")
    application.include_router(widget_page_router)
    application.state.admin_token = secrets.token_urlsafe(32)
    application.add_middleware(LocalWorkspaceMiddleware, state=application.state,
                               max_active_requests=settings.local_max_active_requests,
                               workspace_origin=origin)
    if production:
        application.add_middleware(ProductionAccessMiddleware, origin=origin,
                                   username=settings.workspace_username,
                                   password=settings.workspace_password.get_secret_value())
    application.mount("/admin-assets", StaticFiles(directory=ADMIN_DIRECTORY), name="admin-assets")

    if not production:
        @application.get("/", include_in_schema=False)
        async def index():
            return RedirectResponse("/admin")

    @application.get("/admin", response_class=HTMLResponse, include_in_schema=False)
    async def admin_page():
        text = (ADMIN_DIRECTORY / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(text.replace("__ADMIN_TOKEN__", application.state.admin_token))
    if production:
        application.mount("/", StaticFiles(directory=settings.frontend_dist_dir, html=True), name="frontend")
    return application


app = create_app()
