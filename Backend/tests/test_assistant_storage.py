"""Isolated PostgreSQL checks; never modify the operator's documents or connections."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import insert, select, func
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.config import get_settings
from app.schemas.assistants import AssistantWrite, ConnectionCreate, ConnectionUpdate
from app.services.assistants import (AssistantAccessError, load_assistant_runtime,
                                    list_assistants, list_connections, save_assistant, save_connection,
                                    delete_assistant, delete_connection, AssistantConflict, AssistantNotFound,
                                    stateless_assistant_turn)
from app.storage.conversations import ConversationAccessError, claim_conversation, release_conversation
from app.storage.db import Database
from app.storage.documents import search_similar_chunks
from app.storage.models import Base, Document, DocumentChunk, EMBEDDING_SPACE, ProviderConnection, ChatConversation, AssistantDocument
from tests.helpers import AsyncTestCase, async_test


@unittest.skipUnless(os.environ.get("RUN_DB_TESTS") == "1", "Set RUN_DB_TESTS=1 for PostgreSQL assistant checks")
class AssistantStorageTests(AsyncTestCase):
    def setUp(self):
        super().setUp()
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        settings = get_settings().model_copy(update={"assistant_key_file": Path(self.folder.name) / "master.key"})
        self.database = Database(settings)
        self.schema = "assistant_test_" + uuid4().hex
        self.created = False
        self.addCleanup(lambda: self.runner.run(self.cleanup_database()))
        self.runner.run(self.prepare_database())

    async def prepare_database(self):
        self.assertTrue(await self.database.is_ready(), "Start PostgreSQL first")
        async with self.database.transaction() as connection:
            await connection.execute(CreateSchema(self.schema))
        self.created = True
        self.database._engine = self.database._engine.execution_options(schema_translate_map={None: self.schema})
        async with self.database.transaction() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.documents = (uuid4(), uuid4())
        async with self.database.transaction() as connection:
            for identifier in self.documents:
                await connection.execute(insert(Document).values(id=identifier, filename=str(identifier) + ".pdf",
                    content_sha256=identifier.hex * 2, page_count=1, status="ready"))
                await connection.execute(insert(DocumentChunk).values(id=uuid4(), document_id=identifier, chunk_index=0,
                    page_number=1, content="Events creation uses the Create button.", embedding_space=EMBEDDING_SPACE,
                    embedding=[1.0] + [0.0] * 383))

    async def cleanup_database(self):
        try:
            if self.created:
                assert self.schema.startswith("assistant_test_")
                async with self.database.transaction() as connection:
                    await connection.execute(DropSchema(self.schema, cascade=True))
        finally:
            await self.database.close()

    async def create_assistant(self, documents):
        connection = await save_connection(self.database, ConnectionCreate(name="Groq test", provider="groq", api_key="private-test-key"))
        return await save_assistant(self.database, AssistantWrite(name="HR", model="openai/gpt-oss-120b",
            connection_id=connection.id, document_ids=list(documents)))

    @async_test
    async def test_encrypted_configuration_scope_updates_and_safe_responses(self):
        assistant = await self.create_assistant(self.documents[:1])
        async with self.database.transaction() as connection:
            ciphertext = await connection.scalar(select(ProviderConnection.encrypted_api_key))
        self.assertNotIn("private-test-key", ciphertext)
        self.assertNotIn("private-test-key", json.dumps([item.model_dump(mode="json") for item in await list_connections(self.database)]))
        runtime = await load_assistant_runtime(self.database, assistant.id)
        self.assertEqual(runtime.document_ids, self.documents[:1])
        self.assertEqual(runtime.model_settings.api_key.get_secret_value(), "private-test-key")
        with self.assertRaises(AssistantAccessError):
            await load_assistant_runtime(self.database, assistant.id, [self.documents[1]])
        update = AssistantWrite(**assistant.model_dump(exclude={"id", "provider", "revision", "created_at", "updated_at", "document_ids"}),
                                document_ids=[self.documents[1]])
        saved = await save_assistant(self.database, update, assistant.id)
        self.assertEqual(saved.revision, 2)
        self.assertEqual((await load_assistant_runtime(self.database, assistant.id)).document_ids, self.documents[1:])
        self.assertEqual(len(await list_assistants(self.database, active_only=True)), 1)

    @async_test
    async def test_cache_reuses_decryption_and_refreshes_cross_process_changes(self):
        from app.services.credential_vault import CredentialVault
        assistant = await self.create_assistant(self.documents[:1])
        with patch.object(CredentialVault, "decrypt", wraps=CredentialVault(self.database.settings).decrypt) as decrypt:
            first = await load_assistant_runtime(self.database, assistant.id)
            self.assertIs(await load_assistant_runtime(self.database, assistant.id), first)
            self.assertEqual(decrypt.call_count, 1)
            other = Database(self.database.settings)
            other._engine = other._engine.execution_options(schema_translate_map={None: self.schema})
            try:
                update = AssistantWrite(**assistant.model_dump(exclude={"id", "provider", "revision", "created_at", "updated_at", "document_ids"}),
                                        document_ids=[])
                await save_assistant(other, update, assistant.id)
                refreshed = await load_assistant_runtime(self.database, assistant.id)
                self.assertEqual(refreshed.revision, 2)
                self.assertEqual(refreshed.document_ids, ())
                with self.assertRaises(AssistantAccessError):
                    await load_assistant_runtime(self.database, assistant.id, [self.documents[0]])
                await save_connection(other, ConnectionUpdate(name="Rotated", active=True, api_key="rotated-test-key"), assistant.connection_id)
                rotated = await load_assistant_runtime(self.database, assistant.id)
                self.assertEqual(rotated.connection_revision, 2)
                self.assertEqual(rotated.model_settings.api_key.get_secret_value(), "rotated-test-key")
                await save_connection(other, ConnectionUpdate(name="Disabled", active=False), assistant.connection_id)
                with self.assertRaises(AssistantNotFound):
                    await load_assistant_runtime(self.database, assistant.id)
            finally:
                await other.close()
        self.assertEqual(self.database._engine.pool.checkedout(), 0)

    @async_test
    async def test_semantic_and_hybrid_search_keep_assistant_scope_including_empty(self):
        vector = [1.0] + [0.0] * 383
        for query in (None, "Events creation"):
            matches = await search_similar_chunks(self.database, vector, query=query,
                                                  allowed_document_ids=self.documents[:1])
            self.assertEqual([match.document_id for match in matches], [self.documents[0]])
            empty = await search_similar_chunks(self.database, vector, query=query, allowed_document_ids=())
            self.assertEqual(empty, [])
            excluded = await search_similar_chunks(self.database, vector, query=query,
                document_ids=[self.documents[1]], allowed_document_ids=self.documents[:1])
            self.assertEqual(excluded, [])

    @async_test
    async def test_conversation_cannot_be_reused_for_another_assistant_or_legacy_chat(self):
        identifier, key = uuid4(), "a" * 64
        assistant = (await self.create_assistant(self.documents[:1])).id
        claim = await claim_conversation(self.database, identifier, key, assistant_id=assistant)
        await release_conversation(self.database, claim)
        for other in (None, uuid4()):
            with self.assertRaises(ConversationAccessError):
                await claim_conversation(self.database, identifier, key, assistant_id=other)
        same = await claim_conversation(self.database, identifier, key, assistant_id=assistant)
        await release_conversation(self.database, same)
        legacy = await claim_conversation(self.database, uuid4(), key)
        await release_conversation(self.database, legacy)

    @async_test
    async def test_deletion_preserves_pdfs_blocks_referenced_connections_and_removes_history(self):
        assistant = await self.create_assistant(self.documents[:1])
        with self.assertRaises(AssistantConflict):
            await delete_connection(self.database, assistant.connection_id)
        claim = await claim_conversation(self.database, uuid4(), "a" * 64, assistant_id=assistant.id)
        with self.assertRaises(AssistantConflict):
            await delete_assistant(self.database, assistant.id)
        await release_conversation(self.database, claim)
        await delete_assistant(self.database, assistant.id)
        async with self.database.transaction() as connection:
            self.assertEqual(await connection.scalar(select(func.count()).select_from(Document)), 2)
            self.assertEqual(await connection.scalar(select(func.count()).select_from(DocumentChunk)), 2)
            self.assertEqual(await connection.scalar(select(func.count()).select_from(AssistantDocument)), 0)
            self.assertEqual(await connection.scalar(select(func.count()).select_from(ChatConversation)), 0)
        with self.assertRaises(ConversationAccessError):
            await claim_conversation(self.database, uuid4(), "a" * 64, assistant_id=assistant.id)
        await delete_connection(self.database, assistant.connection_id)
        with self.assertRaises(AssistantNotFound):
            await delete_connection(self.database, assistant.connection_id)
        with self.assertRaises(AssistantNotFound):
            await delete_assistant(self.database, assistant.id)

    @async_test
    async def test_stateless_turn_blocks_deletion_without_holding_connection_and_cleans_up(self):
        assistant = await self.create_assistant(self.documents[:1])
        async with stateless_assistant_turn(self.database, assistant.id):
            self.assertEqual(self.database._engine.pool.checkedout(), 0)
            with self.assertRaises(AssistantConflict):
                await delete_assistant(self.database, assistant.id)
        async with self.database.transaction() as connection:
            self.assertEqual(await connection.scalar(select(func.count()).select_from(ChatConversation)), 0)
        await delete_assistant(self.database, assistant.id)
