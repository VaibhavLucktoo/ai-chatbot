"""Read-only analytics using the existing local administrator boundary."""

import asyncio
import logging
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import SQLAlchemyError
from app.core.local_access import is_workspace_scope, require_admin_token

# Deprecated schema location; retain compatibility for downstream imports.
from app.schemas.metrics import AnalyticsResponse as AnalyticsResponse
from app.schemas.admin import AdminSessionResponse
from app.storage.metrics import read_metrics

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["local admin analytics"])


@router.get(
    "/session",
    response_model=AdminSessionResponse,
    responses={403: {"description": "Local access required."}},
)
async def admin_session(request: Request):
    # Same trust boundary as /admin, which already embeds this ephemeral token.
    if not is_workspace_scope(request.scope):
        raise HTTPException(
            403, "The admin session is only available on the local machine."
        )
    return {"token": request.app.state.admin_token}


@router.get(
    "/metrics",
    response_model=AnalyticsResponse,
    dependencies=[Depends(require_admin_token)],
    responses={
        403: {"description": "Local administrator session required."},
        503: {"description": "Analytics storage is unavailable."},
    },
)
async def admin_metrics(
    request: Request,
    hours: Annotated[int, Query(ge=1, le=720)] = 24,
    model: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    assistant_id: UUID | None = None,
    workspace_only: bool = False,
    provider: Annotated[str | None, Query(min_length=1, max_length=255)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
):
    database = getattr(request.app.state, "database", None)
    if database is None:
        raise HTTPException(503, "Analytics storage is unavailable.")
    if assistant_id is not None and workspace_only:
        raise HTTPException(422, "Choose an assistant or workspace history, not both.")
    try:
        async with asyncio.timeout(10):
            result = await read_metrics(
                database,
                hours=hours,
                model=model,
                assistant_id=assistant_id,
                workspace_only=workspace_only,
                provider=provider,
                offset=offset,
                limit=limit,
            )
    except (SQLAlchemyError, TimeoutError, OSError) as error:
        logger.warning("Analytics read failed (%s)", type(error).__name__)
        raise HTTPException(
            503, "Analytics storage is temporarily unavailable."
        ) from error
    collector = getattr(request.app.state, "metrics", None)
    result["runtime"] = collector.snapshot() if collector is not None else None
    cache = getattr(database, "assistant_cache", None)
    result["configuration_cache"] = cache.snapshot() if cache is not None else None
    result["pricing"] = {
        "currency": "USD",
        "configured_models": sorted(database.settings.metrics_model_prices),
        "basis": "Configured rates per million input/output tokens; estimates exclude discounts and other fees.",
    }
    result["quality"] = {
        "status": "not_evaluated",
        "accuracy": None,
        "citation_support": None,
        "completeness": None,
        "reason": "Accuracy and claim support require labeled evaluations; operational metrics do not measure them.",
    }
    return result
