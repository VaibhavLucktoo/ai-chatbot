from typing import cast

from fastapi import APIRouter, Request, Response, status

from app.schemas.readiness import ReadinessResponse
from app.storage.db import Database

router = APIRouter(tags=["health"])


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def readiness(
    request: Request,
    response: Response,
) -> ReadinessResponse:
    database = cast(Database, request.app.state.database)

    if not await database.is_ready():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(status="not_ready")

    return ReadinessResponse(status="ready")