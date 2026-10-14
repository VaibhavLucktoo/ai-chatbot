import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import URL, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
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
        self.settings = settings
        from app.services.configuration_cache import ConfigurationCache
        self.assistant_cache = ConfigurationCache(
            settings.assistant_cache_ttl_seconds, settings.assistant_cache_max_entries)
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

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Provide a session and release its resources without auto-committing."""
        async with AsyncSession(
            bind=self._engine,
            autoflush=False,
            expire_on_commit=False,
        ) as session:
            yield session

    async def is_ready(self, *, check_schema: bool = False) -> bool:
        """Check database access and the required vector extension."""
        try:
            async with asyncio.timeout(self._health_timeout):
                async with self._engine.connect() as connection:
                    result = await connection.scalar(READINESS_QUERY)
                    if result is not True:
                        return False
                    if check_schema:
                        # A bounded, zero-row query also verifies new schema columns.
                        from app.storage.models import (Document, DocumentChunk, ChatConversation, ChatMetric,
                                                        ModelCallMetric, Assistant, AssistantDocument, ProviderConnection)
                        from sqlalchemy import select
                        await connection.execute(select(Document.id, Document.attempt_id, Document.lease_expires_at,
                                                        Document.original_pdf, Document.processing_metadata, Document.active,
                                                        Document.ingestion_attempts).limit(0))
                        await connection.execute(select(DocumentChunk.id, DocumentChunk.embedding).limit(0))
                        await connection.execute(select(ChatConversation.id, ChatConversation.owner_key_hash,
                                                        ChatConversation.history, ChatConversation.expires_at,
                                                        ChatConversation.attempt_id, ChatConversation.lease_expires_at,
                                                        ChatConversation.assistant_id).limit(0))
                        await connection.execute(select(ChatMetric).limit(0))
                        await connection.execute(select(ModelCallMetric).limit(0))
                        await connection.execute(select(Assistant).limit(0))
                        await connection.execute(select(AssistantDocument).limit(0))
                        await connection.execute(select(ProviderConnection).limit(0))
                    return True

        except (SQLAlchemyError, TimeoutError, OSError) as exc:
            # Avoid logging connection strings, credentials, or SQL inputs.
            logger.warning(
                "Database readiness check failed (%s)",
                type(exc).__name__,
            )
            return False

    async def close(self) -> None:
        """Release pooled connections during application shutdown."""
        await self.assistant_cache.close()
        await self._engine.dispose()
