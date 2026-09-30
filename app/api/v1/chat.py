"""RAG chat endpoint mounted at /v1/chat by the API router."""

import logging
from collections.abc import AsyncIterator
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.llm import (
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)
from app.services.rag import answer_question
from app.services.retrieval import RetrievalProviderError
from app.storage.db import Database


logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


class ChatErrorResponse(BaseModel):
    """Public error body; provider details and credentials are never included."""

    detail: str


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


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Answer a question using uploaded documents",
    responses={
        200: {
            "description": "Answer with sources, or an insufficient-context fallback.",
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
    db: AsyncSession = Depends(get_db_session, scope="function"),
) -> ChatResponse:
    """Retrieve passages and generate an answer with document references.

    FastAPI validates the JSON body before invoking this function. Function
    scope closes the session before the response is sent. The RAG service ends
    its read transaction before model generation, releasing the pooled connection.
    Caller cancellation propagates; logs omit prompts and provider details.
    """
    try:
        return await answer_question(db, request)
    except RetrievalProviderError as exc:
        logger.error("Chat retrieval failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Relevant document passages could not be retrieved.",
        ) from exc
    except (SQLAlchemyError, TimeoutError, OSError) as exc:
        logger.error("Chat storage operation failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document storage is unavailable.",
        ) from exc
    except LLMTimeoutError as exc:
        logger.warning("Chat LLM request timed out (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="The language model timed out. Please try again.",
        ) from exc
    except LLMConnectionError as exc:
        logger.warning("Chat LLM connection failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The language model is temporarily unavailable.",
        ) from exc
    except LLMRateLimitError as exc:
        logger.warning("Chat LLM rate limit reached (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="The language model rate limit was reached. Please retry later.",
        ) from exc
    except LLMError as exc:
        logger.error("Chat LLM provider failed (%s)", type(exc).__name__)
        error_status = status.HTTP_502_BAD_GATEWAY
        detail = "The language model could not produce a valid response."

        if isinstance(exc, LLMResponseError):
            if exc.status_code in (408, 504):
                error_status = status.HTTP_504_GATEWAY_TIMEOUT
                detail = "The language model timed out. Please try again."
            elif exc.status_code == 429:
                error_status = status.HTTP_429_TOO_MANY_REQUESTS
                detail = "The language model rate limit was reached. Please retry later."
            elif exc.status_code == 503:
                error_status = status.HTTP_503_SERVICE_UNAVAILABLE
                detail = "The language model is temporarily unavailable."

        raise HTTPException(status_code=error_status, detail=detail) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unexpected chat failure (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The chat request could not be completed.",
        ) from exc
