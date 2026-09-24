import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import URL, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    create_async_engine,
)

from app.core.config import Settings

logger = logging.getLogger(__name__)

READINESS_QUERY = text(
    "SELECT EXISTS ("
    "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
    ")"
)


class Database:
    def __init__(self, settings: Settings) -> None:
        # URL.create handles special characters in passwords safely.
        url = URL.create(
            drivername="postgresql+psycopg",
            username=settings.postgres_user,
            password=settings.postgres_password.get_secret_value(),
            host=settings.db_host,
            port=settings.db_port,
            database=settings.postgres_db,
        )

        self._health_timeout = settings.db_health_timeout_seconds

        self._engine: AsyncEngine = create_async_engine(
            url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout_seconds,
            pool_pre_ping=True,
            hide_parameters=True,
            connect_args={
                "connect_timeout": settings.db_connect_timeout_seconds,
                "options": (
                    "-c statement_timeout="
                    f"{settings.db_statement_timeout_ms}"
                ),
            },
        )

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncConnection]:
        """Commit on success; roll back if the operation fails."""
        async with self._engine.begin() as connection:
            yield connection

    async def is_ready(self) -> bool:
        """Check database access and the required vector extension."""
        try:
            async with asyncio.timeout(self._health_timeout):
                async with self._engine.connect() as connection:
                    result = await connection.scalar(READINESS_QUERY)
                    return result is True

        except (SQLAlchemyError, TimeoutError, OSError) as exc:
            # Avoid logging connection strings, credentials, or SQL inputs.
            logger.warning(
                "Database readiness check failed (%s)",
                type(exc).__name__,
            )
            return False

    async def close(self) -> None:
        """Release pooled connections during application shutdown."""
        await self._engine.dispose()