"""Assistant selection and token-protected local administrator configuration."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

# Deprecated class import location; preserve existing imports.
from app.api.common.routes import AssistantConfigurationRoute as ConfigurationRoute
from app.core.local_access import require_admin_token
from app.schemas.assistants import (
    AssistantResponse,
    AssistantWrite,
    ConnectionCreate,
    ConnectionResponse,
    ConnectionTest,
    ConnectionUpdate,
    ModelDiscovery,
)
from app.schemas.providers import (
    ProviderListResponse,
    ProviderModelListResponse,
    ProviderTestResponse,
)
from app.schemas.documents import DocumentDetail, DocumentListResponse
from app.services.assistants import list_assistants, save_assistant, delete_assistant
from app.services.provider_service import (
    connection_credentials,
    list_connections,
    save_connection,
    delete_connection,
    discover_models as discover_provider_models,
    list_providers,
    test_provider_connection,
)
from app.storage import document_catalog as catalog_storage


admin_router = APIRouter(
    prefix="/admin",
    tags=["assistant administration"],
    route_class=ConfigurationRoute,
    dependencies=[Depends(require_admin_token)],
)
router = APIRouter(
    prefix="/assistants", tags=["assistants"], route_class=ConfigurationRoute
)


@admin_router.get("/providers", response_model=ProviderListResponse)
async def providers():
    return list_providers()


@admin_router.get("/connections", response_model=list[ConnectionResponse])
async def connections(request: Request):
    return await list_connections(request.app.state.database)


@admin_router.post("/connections", response_model=ConnectionResponse, status_code=201)
async def create_connection(payload: ConnectionCreate, request: Request):
    return await save_connection(request.app.state.database, payload)


@admin_router.put("/connections/{connection_id}", response_model=ConnectionResponse)
async def update_connection(
    connection_id: UUID, payload: ConnectionUpdate, request: Request
):
    return await save_connection(request.app.state.database, payload, connection_id)


@admin_router.delete(
    "/connections/{connection_id}",
    status_code=204,
    response_class=Response,
    responses={
        403: {"description": "Admin access required."},
        404: {"description": "Connection not found."},
        409: {"description": "Connection is referenced by an assistant."},
        503: {"description": "Storage unavailable."},
    },
)
async def remove_connection(connection_id: UUID, request: Request):
    await delete_connection(request.app.state.database, connection_id)
    return Response(status_code=204)


# Deprecated helper location; preserve the previous Request-based signature.
async def discover_models(request: Request, provider: str, key) -> dict:
    return await discover_provider_models(request.app.state.llm_client, provider, key)


@admin_router.post("/connections/models", response_model=ProviderModelListResponse)
async def unsaved_models(payload: ModelDiscovery, request: Request):
    return await discover_provider_models(
        request.app.state.llm_client, payload.provider, payload.api_key
    )


@admin_router.get(
    "/connections/{connection_id}/models", response_model=ProviderModelListResponse
)
async def saved_models(connection_id: UUID, request: Request):
    provider, key = await connection_credentials(
        request.app.state.database, connection_id
    )
    return await discover_provider_models(request.app.state.llm_client, provider, key)


@admin_router.post("/connections/test", response_model=ProviderTestResponse)
async def test_connection(payload: ConnectionTest, request: Request):
    return await test_provider_connection(
        payload,
        database=request.app.state.database,
        client=request.app.state.llm_client,
        slots=request.app.state.llm_slots,
    )


@admin_router.get("/assistants", response_model=list[AssistantResponse])
async def admin_assistants(request: Request):
    return await list_assistants(request.app.state.database)


@admin_router.post("/assistants", response_model=AssistantResponse, status_code=201)
async def create_assistant(payload: AssistantWrite, request: Request):
    return await save_assistant(request.app.state.database, payload)


@admin_router.put("/assistants/{assistant_id}", response_model=AssistantResponse)
async def update_assistant(
    assistant_id: UUID, payload: AssistantWrite, request: Request
):
    return await save_assistant(request.app.state.database, payload, assistant_id)


@admin_router.delete(
    "/assistants/{assistant_id}",
    status_code=204,
    response_class=Response,
    responses={
        403: {"description": "Admin access required."},
        404: {"description": "Assistant not found."},
        409: {"description": "Assistant has an active chat."},
        503: {"description": "Storage unavailable."},
    },
)
async def remove_assistant(assistant_id: UUID, request: Request):
    await delete_assistant(request.app.state.database, assistant_id)
    return Response(status_code=204)


@router.get("", response_model=list[AssistantResponse])
async def available_assistants(request: Request):
    return await list_assistants(request.app.state.database, active_only=True)


@router.get("/{assistant_id}/documents", response_model=DocumentListResponse)
async def assistant_documents(
    assistant_id: UUID,
    request: Request,
    limit: int = Query(default=25, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
):
    total, rows = await catalog_storage.assistant_documents(
        request.app.state.database, assistant_id, limit=limit, offset=offset
    )
    return DocumentListResponse(
        items=[DocumentDetail.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
