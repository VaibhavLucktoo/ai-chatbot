"""Provider connection lifecycle, discovery and connection tests."""

import asyncio
from uuid import UUID, uuid4

import httpx
from pydantic import SecretStr
from sqlalchemy import delete, insert, select, update, func
from sqlalchemy.exc import IntegrityError

from app.providers.registry import PROVIDERS, provider_settings
from app.schemas.assistants import (
    ConnectionCreate,
    ConnectionUpdate,
    ConnectionResponse,
    ConnectionTest,
)
from app.services.configuration_errors import AssistantNotFound, AssistantConflict
from app.services.credential_vault import CredentialVault
from app.services.llm import (
    LLMConnectionError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
    assistant_model_resources,
    generate_llm_response,
    llm_request_resources,
)
from app.storage.db import Database
from app.storage.models import ProviderConnection, Assistant


async def delete_connection(database: Database, identifier: UUID) -> None:
    try:
        async with database.transaction() as connection:
            found = await connection.scalar(
                select(ProviderConnection.id)
                .where(ProviderConnection.id == identifier)
                .with_for_update()
            )
            if found is None:
                raise AssistantNotFound("Provider connection not found.")
            used = await connection.scalar(
                select(Assistant.id)
                .where(Assistant.connection_id == identifier)
                .limit(1)
            )
            if used is not None:
                raise AssistantConflict(
                    "Connection is used by an assistant. Reassign or delete that assistant first, including disabled assistants."
                )
            await connection.execute(
                delete(ProviderConnection).where(ProviderConnection.id == identifier)
            )
    except IntegrityError:
        raise AssistantConflict(
            "Connection is still used by an assistant. Refresh and reassign it before deleting."
        ) from None
    database.assistant_cache.invalidate()


def _connection_columns():
    return [
        ProviderConnection.id,
        ProviderConnection.name,
        ProviderConnection.provider,
        ProviderConnection.active,
        ProviderConnection.revision,
        ProviderConnection.created_at,
        ProviderConnection.updated_at,
    ]


async def list_connections(database: Database) -> list[ConnectionResponse]:
    async with database.transaction() as connection:
        rows = (
            (
                await connection.execute(
                    select(*_connection_columns()).order_by(
                        ProviderConnection.created_at
                    )
                )
            )
            .mappings()
            .all()
        )
    return [ConnectionResponse.model_validate(dict(row)) for row in rows]


async def save_connection(
    database: Database,
    payload: ConnectionCreate | ConnectionUpdate,
    identifier: UUID | None = None,
) -> ConnectionResponse:
    vault = CredentialVault(database.settings)
    if identifier is None:
        identifier = uuid4()
        encrypted = await asyncio.to_thread(
            vault.encrypt,
            payload.api_key,
            provider=payload.provider,
            connection_id=str(identifier),
        )
        values = {
            "id": identifier,
            "name": payload.name,
            "provider": payload.provider,
            "encrypted_api_key": encrypted,
        }
        async with database.transaction() as connection:
            row = (
                (
                    await connection.execute(
                        insert(ProviderConnection)
                        .values(**values)
                        .returning(*_connection_columns())
                    )
                )
                .mappings()
                .one()
            )
    else:
        async with database.transaction() as connection:
            provider = await connection.scalar(
                select(ProviderConnection.provider).where(
                    ProviderConnection.id == identifier
                )
            )
        if provider is None:
            raise AssistantNotFound("Provider connection not found.")
        values = {
            "name": payload.name,
            "active": payload.active,
            "revision": ProviderConnection.revision + 1,
            "updated_at": func.now(),
        }
        if payload.api_key is not None:
            values["encrypted_api_key"] = await asyncio.to_thread(
                vault.encrypt,
                payload.api_key,
                provider=provider,
                connection_id=str(identifier),
            )
        async with database.transaction() as connection:
            row = (
                (
                    await connection.execute(
                        update(ProviderConnection)
                        .where(ProviderConnection.id == identifier)
                        .values(**values)
                        .returning(*_connection_columns())
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise AssistantNotFound("Provider connection not found.")
    database.assistant_cache.invalidate()
    return ConnectionResponse.model_validate(dict(row))


async def connection_credentials(
    database: Database, identifier: UUID
) -> tuple[str, SecretStr]:
    async with database.transaction() as connection:
        row = (
            await connection.execute(
                select(
                    ProviderConnection.provider, ProviderConnection.encrypted_api_key
                ).where(
                    ProviderConnection.id == identifier,
                    ProviderConnection.active.is_(True),
                )
            )
        ).one_or_none()
    if row is None:
        raise AssistantNotFound("Provider connection is missing or disabled.")
    key = await asyncio.to_thread(
        CredentialVault(database.settings).decrypt,
        row.encrypted_api_key,
        provider=row.provider,
        connection_id=str(identifier),
    )
    return row.provider, key


async def discover_models(client: httpx.AsyncClient, provider: str, key) -> dict:
    try:
        async with asyncio.timeout(20):
            response = await client.get(
                PROVIDERS[provider].base_url + "/models",
                headers={"Authorization": "Bearer " + key.get_secret_value()},
                timeout=20,
            )
    except (httpx.TimeoutException, TimeoutError):
        raise LLMTimeoutError("Provider model discovery timed out.") from None
    except httpx.RequestError:
        raise LLMConnectionError("Provider model discovery failed.") from None
    if response.status_code == 429:
        raise LLMRateLimitError()
    if not response.is_success:
        raise LLMResponseError(
            "Provider model discovery was rejected.", status_code=response.status_code
        )
    try:
        data = response.json()["data"]
        if not isinstance(data, list):
            raise ValueError("Invalid model list")
        models = sorted(
            {
                item["id"]
                for item in data[:1000]
                if isinstance(item, dict)
                and isinstance(item.get("id"), str)
                and 0 < len(item["id"]) <= 200
                and not any(
                    word in item["id"].lower()
                    for word in ("embed", "whisper", "tts", "image", "audio", "video")
                )
            }
        )
    except (ValueError, KeyError, TypeError):
        raise LLMResponseError(
            "Provider model discovery returned invalid data."
        ) from None
    return {"items": models}


async def test_provider_connection(payload: ConnectionTest, *, database, client, slots):
    if payload.connection_id is not None:
        provider, key = await connection_credentials(database, payload.connection_id)
    else:
        provider, key = payload.provider, payload.api_key
    config = provider_settings(
        provider,
        payload.model,
        key,
        **payload.model_dump(
            include={
                "max_output_tokens",
                "context_window_tokens",
                "temperature",
                "timeout_seconds",
            }
        ),
    )
    with assistant_model_resources(config), llm_request_resources(client, slots):
        await generate_llm_response(
            "Reply with the word Ready.",
            system_prompt="This is a connection test. Reply briefly.",
        )
    return {"status": "ok", "provider": provider, "model": payload.model}


def list_providers():
    return {
        "items": [
            {"id": preset.id, "name": preset.name} for preset in PROVIDERS.values()
        ]
    }
