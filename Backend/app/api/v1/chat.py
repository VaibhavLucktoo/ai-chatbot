"""RAG chat endpoint mounted at /v1/chat by the API router."""

from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

# Deprecated import locations; keep these aliases until downstream imports migrate.
from app.api.dependencies import (
    get_db_session as get_db_session,
)  # Re-export for backward compatibility.
from app.services.chat_service import (
    run_chat as run_chat,
)  # Re-export for backward compatibility.
from app.schemas.chat import ChatRequest, ChatResponse, ClarificationResponse

router = APIRouter(tags=["chat"])


class ChatErrorResponse(BaseModel):
    """Public error body; provider details and credentials are never included."""

    detail: str


@router.post(
    "/chat",
    response_model=ChatResponse | ClarificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Answer a question using uploaded documents",
    responses={
        403: {
            "model": ChatErrorResponse,
            "description": "Conversation capability invalid or documents outside the assistant's scope.",
        },
        404: {
            "model": ChatErrorResponse,
            "description": "Selected assistant is missing or disabled.",
        },
        409: {
            "model": ChatErrorResponse,
            "description": "Conversation is processing another turn.",
        },
        200: {
            "description": "Answer with sources, an insufficient-context fallback, or document selection.",
        },
        422: {
            "description": "Request body failed validation.",
        },
        429: {
            "model": ChatErrorResponse,
            "description": "LLM provider rate limit exceeded.",
        },
        500: {
            "model": ChatErrorResponse,
            "description": "Retrieval, database, or internal processing failure.",
        },
        502: {
            "model": ChatErrorResponse,
            "description": "LLM provider returned an error or an invalid response.",
        },
        503: {
            "model": ChatErrorResponse,
            "description": "LLM provider is unavailable.",
        },
        504: {
            "model": ChatErrorResponse,
            "description": "LLM request timed out.",
        },
    },
)
async def chat(
    request: ChatRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db_session, scope="function"),
    conversation_key: str | None = Header(
        default=None,
        alias="X-Conversation-Key",
        description="Private capability required when conversation_id is supplied.",
    ),
) -> ChatResponse | ClarificationResponse:
    """Retrieve passages and generate an answer with document references.

    FastAPI validates the JSON body before invoking this function. Function
    scope closes the session before the response is sent. The RAG service ends
    its read transaction before model generation, releasing the pooled connection.
    Caller cancellation propagates; logs omit prompts and provider details.
    """
    return await run_chat(
        db,
        request,
        conversation_database=getattr(http_request.app.state, "database", None),
        conversation_key=conversation_key,
    )
