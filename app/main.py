from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import asyncio
from pathlib import Path
import secrets
from contextlib import suppress

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import httpx

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.storage.db import Database
from app.core.middleware import LocalWorkspaceMiddleware
from app.providers.embeddings import get_embedding_provider
from app.services.recovery import recovery_loop

ADMIN_DIRECTORY = Path(__file__).parent / "admin"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database = Database(get_settings())

    try:
        if not await database.is_ready(check_schema=True):
            raise RuntimeError(
                "Database startup check failed. "
                "Check PostgreSQL, the vector extension, and run alembic upgrade head."
            )

        app.state.database = database
        app.state.embedding_ready = False
        if get_settings().embedding_warmup_on_startup:
            async with asyncio.timeout(get_settings().embedding_timeout_seconds):
                await get_embedding_provider().embed_query("Readiness check")
            app.state.embedding_ready = True
        app.state.llm_slots = asyncio.Semaphore(2)
        async with httpx.AsyncClient(follow_redirects=False, limits=httpx.Limits(
            max_connections=4, max_keepalive_connections=2,
        )) as client:
            app.state.llm_client = client
            recovery = asyncio.create_task(recovery_loop(database), name="ingestion-recovery")
            try:
                yield
            finally:
                recovery.cancel()
                with suppress(asyncio.CancelledError):
                    await recovery
    finally:
        await database.close()
        if get_embedding_provider.cache_info().currsize:
            get_embedding_provider().close()
            get_embedding_provider.cache_clear()


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.app_env == "production":
        raise RuntimeError("Public production mode is unsupported. Use the local workspace or implement authenticated document authorization before exposure.")

    application = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
    )
    application.include_router(api_router, prefix="/v1")
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
