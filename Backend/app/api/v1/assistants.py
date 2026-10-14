"""Assistant selection and token-protected local administrator configuration."""

import asyncio
from collections.abc import Callable
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from app.api.v1.document_catalog import metadata_query
from app.core.local_access import require_admin_token
from app.providers.registry import PROVIDERS, provider_settings
from app.schemas.assistants import (AssistantResponse, AssistantWrite, ConnectionCreate, ConnectionResponse,
                                   ConnectionTest, ConnectionUpdate, ModelDiscovery)
from app.schemas.documents import DocumentDetail, DocumentListResponse
from app.services.assistants import (AssistantAccessError, AssistantConfigurationError, AssistantNotFound, AssistantConflict,
                                    connection_credentials, list_assistants, list_connections,
                                    save_assistant, save_connection, delete_assistant, delete_connection)
from app.services.credential_vault import CredentialError
from app.services.llm import (LLMConnectionError, LLMRateLimitError, LLMResponseError,
                              LLMTimeoutError, assistant_model_resources, generate_llm_response,
                              llm_request_resources)
from app.storage.models import Assistant, AssistantDocument, Document, ProviderConnection


class ConfigurationRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        handler = super().get_route_handler()

        async def safe_handler(request: Request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                # FastAPI's default includes raw input, which may contain API keys.
                return JSONResponse({"detail": [{"loc": error["loc"], "msg": error["msg"],
                                                 "type": error["type"]} for error in exc.errors()]}, status_code=422)
            except AssistantNotFound as exc:
                raise HTTPException(404, str(exc)) from None
            except AssistantAccessError as exc:
                raise HTTPException(403, str(exc)) from None
            except AssistantConfigurationError as exc:
                raise HTTPException(422, str(exc)) from None
            except AssistantConflict as exc:
                raise HTTPException(409, str(exc)) from None
            except CredentialError as exc:
                raise HTTPException(503, str(exc)) from None
            except LLMRateLimitError:
                raise HTTPException(429, "Provider quota or rate limit reached. Retry later.") from None
            except LLMTimeoutError:
                raise HTTPException(504, "The provider connection test timed out.") from None
            except LLMConnectionError:
                raise HTTPException(503, "The provider could not be reached.") from None
            except LLMResponseError as exc:
                if exc.status_code in (408, 504):
                    raise HTTPException(504, "The provider connection timed out.") from None
                if exc.status_code == 503:
                    raise HTTPException(503, "The provider is temporarily unavailable.") from None
                if exc.status_code in (401, 403):
                    raise HTTPException(422, "The provider rejected the API key or model access.") from None
                if exc.status_code in (400, 404):
                    raise HTTPException(422, "The selected model or generation settings are unavailable on this connection.") from None
                raise HTTPException(502, "The provider returned an unusable response.") from None
            except IntegrityError:
                raise HTTPException(409, "Configuration changed while saving. Refresh and try again.") from None
            except (SQLAlchemyError, TimeoutError, OSError):
                raise HTTPException(503, "Assistant configuration storage is temporarily unavailable.") from None

        return safe_handler


admin_router = APIRouter(prefix="/admin", tags=["assistant administration"], route_class=ConfigurationRoute,
                         dependencies=[Depends(require_admin_token)])
router = APIRouter(prefix="/assistants", tags=["assistants"], route_class=ConfigurationRoute)


@admin_router.get("/providers")
async def providers():
    return {"items": [{"id": preset.id, "name": preset.name} for preset in PROVIDERS.values()]}


@admin_router.get("/connections", response_model=list[ConnectionResponse])
async def connections(request: Request):
    return await list_connections(request.app.state.database)


@admin_router.post("/connections", response_model=ConnectionResponse, status_code=201)
async def create_connection(payload: ConnectionCreate, request: Request):
    return await save_connection(request.app.state.database, payload)


@admin_router.put("/connections/{connection_id}", response_model=ConnectionResponse)
async def update_connection(connection_id: UUID, payload: ConnectionUpdate, request: Request):
    return await save_connection(request.app.state.database, payload, connection_id)


@admin_router.delete("/connections/{connection_id}", status_code=204, response_class=Response,
                     responses={403: {"description": "Admin access required."},
                                404: {"description": "Connection not found."},
                                409: {"description": "Connection is referenced by an assistant."},
                                503: {"description": "Storage unavailable."}})
async def remove_connection(connection_id: UUID, request: Request):
    await delete_connection(request.app.state.database, connection_id)
    return Response(status_code=204)


async def discover_models(request: Request, provider: str, key) -> dict:
    client: httpx.AsyncClient = request.app.state.llm_client
    try:
        async with asyncio.timeout(20):
            response = await client.get(PROVIDERS[provider].base_url + "/models",
                                        headers={"Authorization": "Bearer " + key.get_secret_value()}, timeout=20)
    except (httpx.TimeoutException, TimeoutError):
        raise LLMTimeoutError("Provider model discovery timed out.") from None
    except httpx.RequestError:
        raise LLMConnectionError("Provider model discovery failed.") from None
    if response.status_code == 429:
        raise LLMRateLimitError()
    if not response.is_success:
        raise LLMResponseError("Provider model discovery was rejected.", status_code=response.status_code)
    try:
        data = response.json()["data"]
        if not isinstance(data, list):
            raise ValueError("Invalid model list")
        models = sorted({item["id"] for item in data[:1000] if isinstance(item, dict)
                         and isinstance(item.get("id"), str) and 0 < len(item["id"]) <= 200
                         and not any(word in item["id"].lower() for word in ("embed", "whisper", "tts", "image", "audio", "video"))})
    except (ValueError, KeyError, TypeError):
        raise LLMResponseError("Provider model discovery returned invalid data.") from None
    return {"items": models}


@admin_router.post("/connections/models")
async def unsaved_models(payload: ModelDiscovery, request: Request):
    return await discover_models(request, payload.provider, payload.api_key)


@admin_router.get("/connections/{connection_id}/models")
async def saved_models(connection_id: UUID, request: Request):
    provider, key = await connection_credentials(request.app.state.database, connection_id)
    return await discover_models(request, provider, key)


@admin_router.post("/connections/test")
async def test_connection(payload: ConnectionTest, request: Request):
    if payload.connection_id is not None:
        provider, key = await connection_credentials(request.app.state.database, payload.connection_id)
    else:
        provider, key = payload.provider, payload.api_key
    config = provider_settings(provider, payload.model, key,
                               **payload.model_dump(include={"max_output_tokens", "context_window_tokens",
                                                             "temperature", "timeout_seconds"}))
    with assistant_model_resources(config), llm_request_resources(request.app.state.llm_client,
                                                                  request.app.state.llm_slots):
        await generate_llm_response("Reply with the word Ready.", system_prompt="This is a connection test. Reply briefly.")
    return {"status": "ok", "provider": provider, "model": payload.model}


@admin_router.get("/assistants", response_model=list[AssistantResponse])
async def admin_assistants(request: Request):
    return await list_assistants(request.app.state.database)


@admin_router.post("/assistants", response_model=AssistantResponse, status_code=201)
async def create_assistant(payload: AssistantWrite, request: Request):
    return await save_assistant(request.app.state.database, payload)


@admin_router.put("/assistants/{assistant_id}", response_model=AssistantResponse)
async def update_assistant(assistant_id: UUID, payload: AssistantWrite, request: Request):
    return await save_assistant(request.app.state.database, payload, assistant_id)


@admin_router.delete("/assistants/{assistant_id}", status_code=204, response_class=Response,
                     responses={403: {"description": "Admin access required."},
                                404: {"description": "Assistant not found."},
                                409: {"description": "Assistant has an active chat."},
                                503: {"description": "Storage unavailable."}})
async def remove_assistant(assistant_id: UUID, request: Request):
    await delete_assistant(request.app.state.database, assistant_id)
    return Response(status_code=204)


@router.get("", response_model=list[AssistantResponse])
async def available_assistants(request: Request):
    return await list_assistants(request.app.state.database, active_only=True)


@router.get("/{assistant_id}/documents", response_model=DocumentListResponse)
async def assistant_documents(assistant_id: UUID, request: Request,
                              limit: int = Query(default=25, ge=1, le=50),
                              offset: int = Query(default=0, ge=0)):
    async with request.app.state.database.transaction() as connection:
        available = await connection.scalar(select(Assistant.id).join(ProviderConnection).where(
            Assistant.id == assistant_id, Assistant.active.is_(True), ProviderConnection.active.is_(True)))
        if available is None:
            raise AssistantNotFound("Assistant is missing or disabled.")
        filters = [Document.status == "ready", Document.active.is_(True), Document.id.in_(
            select(AssistantDocument.document_id).where(AssistantDocument.assistant_id == assistant_id))]
        total = await connection.scalar(select(func.count()).select_from(Document).where(*filters))
        rows = (await connection.execute(metadata_query().where(*filters).order_by(Document.created_at.desc(), Document.id)
                                        .offset(offset).limit(limit))).mappings().all()
    return DocumentListResponse(items=[DocumentDetail.model_validate(row) for row in rows],
                                total=total, limit=limit, offset=offset)
