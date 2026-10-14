from typing import Literal
from pydantic import BaseModel

class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    message: str = "Service is healthy"