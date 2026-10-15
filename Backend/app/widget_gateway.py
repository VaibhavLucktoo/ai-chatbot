"""Public deployment entry point: widget chat/assets only, no admin or document APIs."""
from fastapi import FastAPI

from app.api.v1.widget_assets import page_router
from app.api.v1.widget_visitor import router
from app.core.config import get_settings
from app.core.lifespan import lifespan
from app.core.middleware import LocalWorkspaceMiddleware


def create_widget_gateway():
    settings = get_settings()
    if not settings.widget_public_enabled or not settings.widget_public_origin.startswith("https://"):
        raise RuntimeError("Enable WIDGET_PUBLIC_ENABLED and configure an HTTPS WIDGET_PUBLIC_ORIGIN before starting the public gateway.")
    application = FastAPI(title="Assistant website widget", lifespan=lifespan,
                          docs_url=None, redoc_url=None, openapi_url=None)
    application.state.widget_only = True
    application.include_router(router, prefix="/v1")
    application.include_router(page_router)
    application.add_middleware(LocalWorkspaceMiddleware, state=application.state,
        max_active_requests=settings.local_max_active_requests, widget_public_enabled=True,
        widget_public_origin=settings.widget_public_origin)
    return application


# Launch as an ASGI factory so importing this module doesn't start or expose a service.
