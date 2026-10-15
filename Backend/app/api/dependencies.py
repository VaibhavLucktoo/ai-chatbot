"""Shared request-scoped database dependencies."""

import logging
from collections.abc import AsyncIterator
from typing import cast

from fastapi import HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.db import Database

# Retain the existing diagnostic logger for compatibility with operators.
logger = logging.getLogger("app.api.v1.chat")


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Use the application database and close the session after this request."""
    database = cast(Database | None, getattr(request.app.state, "database", None))
    if database is None:
        logger.error("Chat database is not initialized")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document storage is unavailable.",
        )

    try:
        async with database.session() as session:
            yield session
    except (SQLAlchemyError, TimeoutError, OSError) as exc:
        logger.error("Chat database session failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document storage is unavailable.",
        ) from exc
