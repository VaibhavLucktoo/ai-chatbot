from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.storage.db import Database


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database = Database(get_settings())

    try:
        if not await database.is_ready():
            raise RuntimeError(
                "Database startup check failed. "
                "Check PostgreSQL connectivity and the vector extension."
            )

        app.state.database = database
        yield
    finally:
        await database.close()


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
    )
    application.include_router(api_router, prefix="/v1")
    return application


app = create_app()