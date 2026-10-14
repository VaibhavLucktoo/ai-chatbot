"""Local assistant configuration, short SQL transactions and immutable chat snapshots."""

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from pydantic import SecretStr
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from app.providers.registry import ProviderModelSettings, provider_settings
from app.schemas.assistants import AssistantResponse, AssistantWrite, ConnectionCreate, ConnectionResponse, ConnectionUpdate
from app.services.credential_vault import CredentialVault
from app.storage.db import Database
from app.storage.models import Assistant, AssistantDocument, ProviderConnection, Document, ChatConversation

logger = logging.getLogger(__name__)


class AssistantNotFound(RuntimeError):
    pass


class AssistantAccessError(RuntimeError):
    pass


class AssistantConfigurationError(RuntimeError):
    pass


class AssistantConflict(RuntimeError):
    pass


async def delete_connection(database: Database, identifier: UUID) -> None:
    try:
        async with database.transaction() as connection:
            found = await connection.scalar(select(ProviderConnection.id).where(
                ProviderConnection.id == identifier).with_for_update())
            if found is None:
                raise AssistantNotFound("Provider connection not found.")
            used = await connection.scalar(select(Assistant.id).where(Assistant.connection_id == identifier).limit(1))
            if used is not None:
                raise AssistantConflict("Connection is used by an assistant. Reassign or delete that assistant first, including disabled assistants.")
            await connection.execute(delete(ProviderConnection).where(ProviderConnection.id == identifier))
    except IntegrityError:
        raise AssistantConflict("Connection is still used by an assistant. Refresh and reassign it before deleting.") from None
    database.assistant_cache.invalidate()


async def delete_assistant(database: Database, identifier: UUID) -> None:
    async with database.transaction() as connection:
        found = await connection.scalar(select(Assistant.id).where(Assistant.id == identifier).with_for_update())
        if found is None:
            raise AssistantNotFound("Assistant not found.")
        busy = await connection.scalar(select(ChatConversation.id).where(
            ChatConversation.assistant_id == identifier, ChatConversation.attempt_id.is_not(None),
            ChatConversation.lease_expires_at > func.now()).limit(1))
        if busy is not None:
            raise AssistantConflict("This assistant has an active chat. Wait for it to finish before deleting.")
        await connection.execute(delete(ChatConversation).where(ChatConversation.assistant_id == identifier))
        # The FK cascades assignments; documents, chunks, connections and metrics remain.
        await connection.execute(delete(Assistant).where(Assistant.id == identifier))
    database.assistant_cache.invalidate(identifier)


@asynccontextmanager
async def stateless_assistant_turn(database: Database, identifier: UUID):
    """A durable short lease protects stateless turns without holding a connection."""
    from app.storage.conversations import claim_conversation
    claim = await claim_conversation(database, uuid4(), secrets.token_hex(32), assistant_id=identifier)
    try:
        yield
    finally:
        async def cleanup():
            async with database.transaction() as connection:
                await connection.execute(delete(ChatConversation).where(
                    ChatConversation.id == claim.id, ChatConversation.attempt_id == claim.attempt_id))
        try:
            await asyncio.shield(cleanup())
        except Exception as exc:
            # A failed cleanup leaves only a bounded lease, never a saved transcript.
            logger.warning("Stateless assistant lease cleanup failed (%s)", type(exc).__name__)


@dataclass(frozen=True)
class AssistantRuntime:
    id: UUID
    revision: int
    connection_id: UUID
    connection_revision: int
    document_ids: tuple[UUID, ...]
    model_settings: ProviderModelSettings = field(repr=False)
    name: str = ""
    provider: str = ""


def _connection_columns():
    return [ProviderConnection.id, ProviderConnection.name, ProviderConnection.provider,
            ProviderConnection.active, ProviderConnection.revision,
            ProviderConnection.created_at, ProviderConnection.updated_at]


async def list_connections(database: Database) -> list[ConnectionResponse]:
    async with database.transaction() as connection:
        rows = (await connection.execute(select(*_connection_columns()).order_by(ProviderConnection.created_at))).mappings().all()
    return [ConnectionResponse.model_validate(dict(row)) for row in rows]


async def save_connection(database: Database, payload: ConnectionCreate | ConnectionUpdate,
                          identifier: UUID | None = None) -> ConnectionResponse:
    vault = CredentialVault(database.settings)
    if identifier is None:
        identifier = uuid4()
        encrypted = await asyncio.to_thread(vault.encrypt, payload.api_key,
                                             provider=payload.provider, connection_id=str(identifier))
        values = {"id": identifier, "name": payload.name, "provider": payload.provider,
                  "encrypted_api_key": encrypted}
        async with database.transaction() as connection:
            row = (await connection.execute(insert(ProviderConnection).values(**values)
                                            .returning(*_connection_columns()))).mappings().one()
    else:
        async with database.transaction() as connection:
            provider = await connection.scalar(select(ProviderConnection.provider).where(ProviderConnection.id == identifier))
        if provider is None:
            raise AssistantNotFound("Provider connection not found.")
        values = {"name": payload.name, "active": payload.active,
                  "revision": ProviderConnection.revision + 1, "updated_at": func.now()}
        if payload.api_key is not None:
            values["encrypted_api_key"] = await asyncio.to_thread(vault.encrypt, payload.api_key,
                                                                  provider=provider, connection_id=str(identifier))
        async with database.transaction() as connection:
            row = (await connection.execute(update(ProviderConnection).where(ProviderConnection.id == identifier)
                                            .values(**values).returning(*_connection_columns()))).mappings().one_or_none()
        if row is None:
            raise AssistantNotFound("Provider connection not found.")
    database.assistant_cache.invalidate()
    return ConnectionResponse.model_validate(dict(row))


async def connection_credentials(database: Database, identifier: UUID) -> tuple[str, SecretStr]:
    async with database.transaction() as connection:
        row = (await connection.execute(select(ProviderConnection.provider, ProviderConnection.encrypted_api_key)
                                        .where(ProviderConnection.id == identifier, ProviderConnection.active.is_(True)))).one_or_none()
    if row is None:
        raise AssistantNotFound("Provider connection is missing or disabled.")
    key = await asyncio.to_thread(CredentialVault(database.settings).decrypt, row.encrypted_api_key,
                                  provider=row.provider, connection_id=str(identifier))
    return row.provider, key


async def list_assistants(database: Database, *, active_only: bool = False) -> list[AssistantResponse]:
    statement = select(*Assistant.__table__.c, ProviderConnection.provider).join(
        ProviderConnection, ProviderConnection.id == Assistant.connection_id)
    if active_only:
        statement = statement.where(Assistant.active.is_(True), ProviderConnection.active.is_(True))
    async with database.transaction() as connection:
        rows = (await connection.execute(statement.order_by(Assistant.created_at))).mappings().all()
        scopes = (await connection.execute(select(AssistantDocument).where(
            AssistantDocument.assistant_id.in_([row["id"] for row in rows])))).mappings().all() if rows else []
    documents: dict[UUID, list[UUID]] = {}
    for scope in scopes:
        documents.setdefault(scope["assistant_id"], []).append(scope["document_id"])
    return [AssistantResponse.model_validate({**dict(row), "document_ids": documents.get(row["id"], [])}) for row in rows]


async def save_assistant(database: Database, payload: AssistantWrite,
                         identifier: UUID | None = None) -> AssistantResponse:
    values = payload.model_dump(exclude={"document_ids"})
    create = identifier is None
    identifier = identifier or uuid4()
    async with database.transaction() as connection:
        provider = await connection.scalar(select(ProviderConnection.provider).where(ProviderConnection.id == payload.connection_id))
        if provider is None:
            raise AssistantConfigurationError("Choose an existing provider connection.")
        existing_documents = set((await connection.execute(select(Document.id).where(
            Document.id.in_(payload.document_ids)))).scalars().all())
        if existing_documents != set(payload.document_ids):
            raise AssistantConfigurationError("One or more assigned documents no longer exist.")
        if create:
            statement = insert(Assistant).values(id=identifier, **values)
        else:
            # Serialize assignment replacement and revision changes for this assistant.
            found = await connection.scalar(select(Assistant.id).where(Assistant.id == identifier).with_for_update())
            if found is None:
                raise AssistantNotFound("Assistant not found.")
            statement = update(Assistant).where(Assistant.id == identifier).values(
                **values, revision=Assistant.revision + 1, updated_at=func.now())
        row = (await connection.execute(statement.returning(*Assistant.__table__.c))).mappings().one()
        await connection.execute(delete(AssistantDocument).where(AssistantDocument.assistant_id == identifier))
        if payload.document_ids:
            await connection.execute(insert(AssistantDocument), [
                {"assistant_id": identifier, "document_id": document_id} for document_id in payload.document_ids])
    database.assistant_cache.invalidate(identifier)
    return AssistantResponse.model_validate({**dict(row), "provider": provider, "document_ids": payload.document_ids})


async def load_assistant_runtime(database: Database, identifier: UUID,
                                 selected_documents: list[UUID] | None = None) -> AssistantRuntime:
    runtime, hit = await database.assistant_cache.get(identifier, lambda: _read_assistant_runtime(database, identifier))
    if hit:
        # A cheap indexed revision check catches edits from other workers as well.
        # It excludes assignments and ciphertext; the connection is released here.
        async with database.transaction() as connection:
            versions = (await connection.execute(select(Assistant.revision, ProviderConnection.revision)
                .join(ProviderConnection, ProviderConnection.id == Assistant.connection_id).where(
                    Assistant.id == identifier, Assistant.active.is_(True), ProviderConnection.active.is_(True)
                ))).one_or_none()
        if versions is None:
            database.assistant_cache.invalidate(identifier)
            raise AssistantNotFound("Assistant is missing or disabled.")
        if tuple(versions) != (runtime.revision, runtime.connection_revision):
            database.assistant_cache.invalidate(identifier)
            runtime, _ = await database.assistant_cache.get(identifier, lambda: _read_assistant_runtime(database, identifier))
    if selected_documents is not None and not set(selected_documents).issubset(runtime.document_ids):
        raise AssistantAccessError("The selected documents are not assigned to this assistant.")
    return runtime


async def _read_assistant_runtime(database: Database, identifier: UUID) -> AssistantRuntime:
    async with database.transaction() as connection:
        # One consistent snapshot for model, connection and assigned-document scope.
        from sqlalchemy import text
        await connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        row = (await connection.execute(select(
            *Assistant.__table__.c,
            ProviderConnection.provider,
            ProviderConnection.encrypted_api_key,
            ProviderConnection.revision.label("connection_revision"),
        ).join(ProviderConnection, ProviderConnection.id == Assistant.connection_id).where(
            Assistant.id == identifier, Assistant.active.is_(True), ProviderConnection.active.is_(True)
        ))).mappings().one_or_none()
        if row is None:
            raise AssistantNotFound("Assistant is missing or disabled.")
        documents = tuple((await connection.execute(select(AssistantDocument.document_id).where(
            AssistantDocument.assistant_id == identifier))).scalars().all())
    key = await asyncio.to_thread(CredentialVault(database.settings).decrypt, row["encrypted_api_key"],
                                  provider=row["provider"], connection_id=str(row["connection_id"]))
    settings = provider_settings(row["provider"], row["model"], key,
                                 max_output_tokens=row["max_output_tokens"],
                                 context_window_tokens=row["context_window_tokens"],
                                 temperature=row["temperature"], timeout_seconds=row["timeout_seconds"])
    return AssistantRuntime(identifier, row["revision"], row["connection_id"],
                            row["connection_revision"], documents, settings, row["name"], row["provider"])
