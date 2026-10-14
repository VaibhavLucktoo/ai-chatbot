"""RAG chat endpoint mounted at /v1/chat by the API router."""

import logging
from collections.abc import AsyncIterator
from typing import cast

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.chat import ChatRequest, ChatResponse, ClarificationResponse
from app.services.llm import (
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
    assistant_model_resources,
)
from app.services.rag import answer_question
from app.services.conversations import answer_conversation
from app.storage.conversations import ConversationAccessError, ConversationBusyError
from app.services.retrieval import RetrievalProviderError
from app.storage.db import Database
from app.services.assistants import AssistantAccessError, AssistantNotFound, load_assistant_runtime, stateless_assistant_turn
from app.services.credential_vault import CredentialError


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
    response_model=ChatResponse | ClarificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Answer a question using uploaded documents",
    responses={
        403: {"model": ChatErrorResponse, "description": "Conversation capability invalid or documents outside the assistant's scope."},
        404: {"model": ChatErrorResponse, "description": "Selected assistant is missing or disabled."},
        409: {"model": ChatErrorResponse, "description": "Conversation is processing another turn."},
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
    conversation_key: str | None = Header(default=None, alias="X-Conversation-Key", description="Private capability required when conversation_id is supplied."),
) -> ChatResponse | ClarificationResponse:
    """Retrieve passages and generate an answer with document references.

    FastAPI validates the JSON body before invoking this function. Function
    scope closes the session before the response is sent. The RAG service ends
    its read transaction before model generation, releasing the pooled connection.
    Caller cancellation propagates; logs omit prompts and provider details.
    """
    return await run_chat(db, request,
                          conversation_database=getattr(http_request.app.state, "database", None),
                          conversation_key=conversation_key)


async def run_chat(db: AsyncSession, request: ChatRequest, *, trace: dict | None = None,
                   conversation_database=None, conversation_key: str | None = None):
    """Share the public error mapping with the local diagnostic console."""
    try:
        assistant = None
        from app.services.metrics import current_request
        measurement = current_request()
        if measurement is not None:
            # Preserve the selected ID even when loading fails; never copy the body.
            measurement.assistant_id = request.assistant_id
        if request.assistant_id is not None:
            if conversation_database is None:
                raise HTTPException(503, "Assistant configuration storage is unavailable.")
            assistant = await load_assistant_runtime(conversation_database, request.assistant_id, request.document_ids)
            if measurement is not None:
                measurement.assistant_name = assistant.name
                measurement.assistant_revision = assistant.revision
                measurement.connection_id = assistant.connection_id
                measurement.connection_revision = assistant.connection_revision
                measurement.configured_provider = assistant.provider
                measurement.configured_model = assistant.model_settings.model
        options = {"assistant": assistant} if assistant is not None else {}
        with assistant_model_resources(assistant.model_settings if assistant is not None else None):
            if request.conversation_id is not None:
                if conversation_key is None:
                    raise ConversationAccessError("A conversation key is required. Start a new chat.")
                if conversation_database is None:
                    raise HTTPException(status_code=500, detail="Conversation storage is unavailable.")
                return await answer_conversation(conversation_database, db, request, conversation_key, trace=trace, **options)
            if assistant is not None:
                async with stateless_assistant_turn(conversation_database, assistant.id):
                    return await answer_question(db, request, trace=trace, **options)
            if trace is None:
                return await answer_question(db, request, **options)
            return await answer_question(db, request, trace=trace, **options)
    except AssistantNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except AssistantAccessError as exc:
        raise HTTPException(403, str(exc)) from exc
    except CredentialError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ConversationAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ConversationBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc), headers={"Retry-After": "2"}) from exc
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
