from pathlib import Path
import secrets

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.middleware import LocalWorkspaceMiddleware
from app.core.lifespan import lifespan
from app.api.v1.widgets import page_router as widget_page_router

ADMIN_DIRECTORY = Path(__file__).parent / "admin"


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.app_env == "production":
        raise RuntimeError("Public production mode is unsupported. Use the local workspace or implement authenticated document authorization before exposure.")

    application = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
    )
    application.include_router(api_router, prefix="/v1")
    application.include_router(widget_page_router)
    application.state.admin_token = secrets.token_urlsafe(32)
    application.add_middleware(LocalWorkspaceMiddleware, state=application.state,
                               max_active_requests=settings.local_max_active_requests)
    application.mount("/admin-assets", StaticFiles(directory=ADMIN_DIRECTORY), name="admin-assets")

    @application.get("/", include_in_schema=False)
    async def index():
        return RedirectResponse("/admin")

    @application.get("/admin", response_class=HTMLResponse, include_in_schema=False)
    async def admin_page():
        text = (ADMIN_DIRECTORY / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(text.replace("__ADMIN_TOKEN__", application.state.admin_token))
    return application


app = create_app()
