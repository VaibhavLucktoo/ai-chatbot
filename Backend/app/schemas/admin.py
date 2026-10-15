"""Typed local administrator responses, preserving existing JSON values."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.chat import ChatResponse, ClarificationResponse


class AdminSessionResponse(BaseModel):
    token: str


class AdminStatusResponse(BaseModel):
    database_ready: bool
    model: str
    temperature: float
    max_output_tokens: int
    generation_timeout_seconds: float
    mode: Literal["local"]
    conversation_memory: bool


class AdminDocument(BaseModel):
    id: str
    filename: str
    page_count: int
    status: str
    # The existing encoder emits +00:00, whereas datetime models emit Z.
    created_at: str = Field(json_schema_extra={"format": "date-time"})
    active: bool
    processing_metadata: Any
    chunk_count: int
    lease_active: bool | None
    recoverable: bool


class AdminDocumentListResponse(BaseModel):
    items: list[AdminDocument]
    total: int
    limit: int
    offset: int


class AdminChatResponse(BaseModel):
    status: Literal["clarification_required", "insufficient_context", "answered"]
    response: ChatResponse | ClarificationResponse
    diagnostics: dict[str, Any]
