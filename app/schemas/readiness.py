from typing import Literal

from pydantic import BaseModel


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]