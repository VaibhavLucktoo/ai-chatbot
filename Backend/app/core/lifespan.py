"""Shared resources for the local console and the isolated widget gateway."""
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI

from app.core.config import get_settings
from app.providers.embeddings import get_embedding_provider
from app.services.metrics import MetricsCollector
from app.services.recovery import recovery_loop
from app.storage.db import Database


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database = Database(get_settings())
    try:
        if not await database.is_ready(check_schema=True):
            raise RuntimeError("Database startup check failed. Check PostgreSQL, the vector extension, and run alembic upgrade head.")
        app.state.database = database
        app.state.metrics = MetricsCollector(database)
        app.state.embedding_ready = False
        if get_settings().embedding_warmup_on_startup:
            async with asyncio.timeout(get_settings().embedding_timeout_seconds):
                await get_embedding_provider().embed_query("Readiness check")
            app.state.embedding_ready = True
        app.state.llm_slots = asyncio.Semaphore(2)
        async with httpx.AsyncClient(follow_redirects=False, limits=httpx.Limits(max_connections=4, max_keepalive_connections=2)) as client:
            app.state.llm_client = client
            # Only the local operator service recovers ingestion jobs.
            recovery = None if getattr(app.state, "widget_only", False) else asyncio.create_task(recovery_loop(database), name="ingestion-recovery")
            app.state.metrics.start()
            try:
                yield
            finally:
                if recovery is not None:
                    recovery.cancel()
                    with suppress(asyncio.CancelledError):
                        await recovery
                await app.state.metrics.close()
    finally:
        await database.close()
        if get_embedding_provider.cache_info().currsize:
            get_embedding_provider().close()
            get_embedding_provider.cache_clear()
