from fastapi import APIRouter
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])

@router.get("/health",response_model= HealthResponse)
async def health()-> HealthResponse:
    """
    Health check endpoint to verify if the service is running.
    """
    return HealthResponse()