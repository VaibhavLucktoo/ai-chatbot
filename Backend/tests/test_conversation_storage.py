"""Real PostgreSQL memory, capabilities, concurrency and API compatibility."""
import asyncio
import json
import os
import unittest
from dataclasses import asdict
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi import FastAPI
from sqlalchemy import func, select, update
from sqlalchemy.schema import CreateSchema, DropSchema
from app.api.v1.chat import router
from app.core.config import get_settings
from app.services import rag, conversation_intent
from app.storage.conversations import (
    ConversationAccessError, ConversationBusyError, claim_conversation, finish_conversation, release_conversation,
)
from app.storage.db import Database
from app.storage.models import ChatConversation
from tests.helpers import AsyncTestCase, async_test
from tests.test_conversation import previous_turn
from tests.test_rag_service import stored_chunk


@unittest.skipUnless(os.environ.get("RUN_DB_TESTS") == "1", "Set RUN_DB_TESTS=1 for PostgreSQL memory checks")
class ConversationStorageTests(AsyncTestCase):
    def setUp(self):
        super().setUp()
        self.database = Database(get_settings())
        self.schema = "conversation_test_" + uuid4().hex
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
            await connection.run_sync(ChatConversation.__table__.create)

    async def cleanup_database(self):
        try:
            if self.created:
                assert self.schema.startswith("conversation_test_")
                async with self.database.transaction() as connection:
                    await connection.execute(DropSchema(self.schema, cascade=True))
        finally:
            await self.database.close()

    def client(self):
        app = FastAPI()
        app.state.database = self.database
        app.include_router(router, prefix="/v1")
        return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test")

    @async_test
    async def test_session_capability_history_continuity_and_isolation(self):
        identifier, key = uuid4(), "a" * 64
        claim = await claim_conversation(self.database, identifier, key)
        await finish_conversation(self.database, claim, previous_turn())
        for unauthorized in (None, "invalid", "b" * 64):
            with self.assertRaises(ConversationAccessError):
                await claim_conversation(self.database, identifier, unauthorized)
        restored = await claim_conversation(self.database, identifier, key)
        self.assertEqual(restored.history, (previous_turn(),))
        await release_conversation(self.database, restored)
        isolated = await claim_conversation(self.database, uuid4(), "c" * 64)
        self.assertEqual(isolated.history, ())
        await release_conversation(self.database, isolated)

    @async_test
    async def test_concurrent_claims_and_expired_attempt_cannot_overwrite(self):
        identifier, key = uuid4(), "a" * 64
        first = await claim_conversation(self.database, identifier, key)
        outcomes = await asyncio.gather(*[claim_conversation(self.database, identifier, key) for _ in range(2)], return_exceptions=True)
        self.assertTrue(all(isinstance(outcome, ConversationBusyError) for outcome in outcomes))
        async with self.database.transaction() as connection:
            await connection.execute(update(ChatConversation).where(ChatConversation.id == identifier).values(lease_expires_at=func.now() - timedelta(seconds=1)))
        current = await claim_conversation(self.database, identifier, key)
        with self.assertRaises(ConversationBusyError):
            await finish_conversation(self.database, first, previous_turn(answer="stale"))
        await release_conversation(self.database, first)
        await finish_conversation(self.database, current, previous_turn(answer="current"))
        restored = await claim_conversation(self.database, identifier, key)
        self.assertEqual(restored.history[0].answer, "current")
        await release_conversation(self.database, restored)

    @async_test
    async def test_expiry_discards_old_history_and_limits_completed_turns(self):
        identifier, key = uuid4(), "a" * 64
        for index in range(9):
            claim = await claim_conversation(self.database, identifier, key)
            await finish_conversation(self.database, claim, previous_turn(question=str(index)))
        claim = await claim_conversation(self.database, identifier, key)
        self.assertEqual(len(claim.history), self.database.settings.conversation_max_turns)
        await release_conversation(self.database, claim)
        async with self.database.transaction() as connection:
            await connection.execute(update(ChatConversation).where(ChatConversation.id == identifier).values(expires_at=func.now() - timedelta(seconds=1)))
        expired = await claim_conversation(self.database, identifier, key)
        self.assertEqual(expired.history, ())
        await release_conversation(self.database, expired)

    @async_test
    async def test_history_survives_a_new_database_instance(self):
        identifier, key = uuid4(), "a" * 64
        claim = await claim_conversation(self.database, identifier, key)
        await finish_conversation(self.database, claim, previous_turn())
        other = Database(get_settings())
        other._engine = other._engine.execution_options(schema_translate_map={None: self.schema})
        try:
            restored = await claim_conversation(other, identifier, key)
            self.assertEqual(restored.history, (previous_turn(),))
            await release_conversation(other, restored)
        finally:
            await other.close()

    @async_test
    async def test_api_legacy_and_memory_responses_and_conflict_mapping(self):
        identifier, key = uuid4(), "a" * 64
        payload = {"question": "Hello", "conversation_id": str(identifier)}
        headers = {"X-Conversation-Key": key}
        async with self.client() as client:
            legacy = await client.post("/v1/chat", json={"question": "Hello"})
            current = await client.post("/v1/chat", json=payload, headers=headers)
            self.assertEqual(legacy.status_code, 200)
            self.assertEqual(current.json(), legacy.json())
            self.assertEqual(set(current.json()), {"answer", "sources"})
            self.assertEqual((await client.post("/v1/chat", json=payload)).status_code, 403)
            self.assertEqual((await client.post("/v1/chat", json=payload, headers={"X-Conversation-Key": "b" * 64})).status_code, 403)
            claim = await claim_conversation(self.database, identifier, key)
            busy = await client.post("/v1/chat", json=payload, headers=headers)
            self.assertEqual(busy.status_code, 409)
            self.assertEqual(busy.headers["Retry-After"], "2")
            await release_conversation(self.database, claim)

    @async_test
    async def test_api_grounded_follow_up_uses_persisted_scope_without_open_connection(self):
        identifier, document_id, key = uuid4(), uuid4(), "a" * 64
        chunk = asdict(stored_chunk(content="1. Open Events. 2. Select Create."))
        chunk["document_id"] = document_id
        answer = json.dumps({"answer": "1. Open Events. 2. Select Create.", "source_numbers": [1]})
        async def generate(*args, **kwargs):
            self.assertEqual(self.database._engine.pool.checkedout(), 0)
            return answer
        with patch.object(rag, "search_similar_chunks", return_value=[chunk]) as retrieve, \
             patch.object(rag, "generate_llm_response", side_effect=generate), \
             patch.object(conversation_intent, "generate_llm_response", return_value='{"question":"How do I select Create in Events?","needs_clarification":false}'):
            async with self.client() as client:
                headers = {"X-Conversation-Key": key}
                first = await client.post("/v1/chat", headers=headers, json={"question": "How do I create an event?", "conversation_id": str(identifier), "document_ids": [str(document_id)]})
                second = await client.post("/v1/chat", headers=headers, json={"question": "Explain the second step again.", "conversation_id": str(identifier), "top_k": 3})
                self.assertEqual(first.status_code, 200, first.text)
                self.assertEqual(second.status_code, 200, second.text)
                self.assertEqual(second.json()["sources"][0]["document_id"], str(document_id))
                self.assertEqual(retrieve.await_args.kwargs["document_ids"], [document_id])
                self.assertEqual(retrieve.await_args.kwargs["top_k"], 3)
        async with self.database.transaction() as connection:
            history = await connection.scalar(select(ChatConversation.history).where(ChatConversation.id == identifier))
            self.assertEqual(len(history), 2)
            self.assertEqual(history[-1]["intent"], "follow_up")
