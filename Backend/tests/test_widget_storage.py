"""Actual PostgreSQL capabilities/budgets in a disposable schema."""
import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from cryptography.fernet import Fernet
from pydantic import SecretStr
from fastapi import HTTPException
from fastapi import FastAPI
import httpx
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.config import get_settings
from app.schemas.assistants import AssistantWrite, ConnectionCreate
from app.schemas.widgets import WidgetWrite
from app.services.assistants import save_assistant, save_connection
from app.services.widgets import admin_widget, start_visitor, visitor, remember_sources, visitor_passage, widget_page
from app.storage.db import Database
from app.storage.models import Base, Assistant, ChatConversation, Document, DocumentChunk, AssistantDocument, WebsiteWidget, WidgetSession, EMBEDDING_SPACE
from tests.helpers import AsyncTestCase, async_test


@unittest.skipUnless(os.environ.get("RUN_DB_TESTS") == "1", "Set RUN_DB_TESTS=1 for widget persistence checks")
class WidgetStorageTests(AsyncTestCase):
    def setUp(self):
        super().setUp()
        self.database = Database(get_settings().model_copy(update={"assistant_encryption_key": SecretStr(Fernet.generate_key().decode())}))
        self.schema = "widget_test_" + uuid4().hex
        self.created = False
        self.addCleanup(lambda: self.runner.run(self.cleanup_database()))
        self.runner.run(self.prepare())

    async def prepare(self):
        async with self.database.transaction() as connection:
            await connection.execute(CreateSchema(self.schema))
        self.created = True
        self.database._engine = self.database._engine.execution_options(schema_translate_map={None: self.schema})
        async with self.database.transaction() as connection:
            await connection.run_sync(Base.metadata.create_all)
        saved = await save_connection(self.database, ConnectionCreate(name="Widget fixture", provider="groq", api_key="private-test-key"))
        self.documents, self.chunks = [uuid4(), uuid4()], [uuid4(), uuid4()]
        async with self.database.transaction() as connection:
            for document, chunk in zip(self.documents, self.chunks):
                await connection.execute(insert(Document).values(id=document, filename="fixture.pdf", content_sha256=document.hex * 2, page_count=1, status="ready"))
                await connection.execute(insert(DocumentChunk).values(id=chunk, document_id=document, chunk_index=0, page_number=1,
                    content="Source evidence", embedding_space=EMBEDDING_SPACE, embedding=[1.0] + [0.0] * 383))
        self.assistant = await save_assistant(self.database, AssistantWrite(name="Website assistant", model="model", connection_id=saved.id, document_ids=self.documents[:1]))
        self.payload = WidgetWrite(enabled=True, allowed_origins=["https://shop.example.com"], requests_per_minute=2, requests_per_day=3)
        self.widget = await admin_widget(self.database, self.assistant.id, self.payload)

    async def cleanup_database(self):
        try:
            if self.created:
                assert self.schema.startswith("widget_test_")
                async with self.database.transaction() as connection:
                    await connection.execute(DropSchema(self.schema, cascade=True))
        finally:
            await self.database.close()

    async def start(self):
        return await start_visitor(self.database, self.widget.id, "https://shop.example.com")

    async def auth(self, session, **options):
        return await visitor(self.database, self.widget.id, session["session_id"], session["token"], **options)

    @async_test
    async def test_private_sessions_isolate_tokens_widgets_and_conversations(self):
        first, second = await self.start(), await self.start()
        a, b = await self.auth(first), await self.auth(second)
        self.assertNotEqual(a[1]["conversation_id"], b[1]["conversation_id"])
        async with self.database.transaction() as connection:
            digest = await connection.scalar(select(WidgetSession.token_hash).where(WidgetSession.id == first["session_id"]))
        self.assertNotEqual(digest, first["token"])
        for identifier, token in ((first["session_id"], second["token"]), (second["session_id"], first["token"]), (first["session_id"], None)):
            with self.assertRaises(HTTPException) as denied:
                await visitor(self.database, self.widget.id, identifier, token)
            self.assertEqual(denied.exception.status_code, 403)
        with self.assertRaises(HTTPException):
            await start_visitor(self.database, self.widget.id, "https://evil.example.com")

    @async_test
    async def test_disable_configuration_changes_and_expiry_revoke_sessions(self):
        session = await self.start()
        await admin_widget(self.database, self.assistant.id, self.payload.model_copy(update={"title": "New title"}))
        with self.assertRaises(HTTPException):
            await self.auth(session)
        session = await self.start()
        async with self.database.transaction() as connection:
            await connection.execute(update(WidgetSession).where(WidgetSession.id == session["session_id"]).values(expires_at=func.now()))
        with self.assertRaises(HTTPException):
            await self.auth(session)
        await admin_widget(self.database, self.assistant.id, self.payload.model_copy(update={"enabled": False}))
        with self.assertRaises(HTTPException) as denied:
            await widget_page(self.database, self.widget.id, "https://shop.example.com")
        self.assertEqual(denied.exception.status_code, 404)

    @async_test
    async def test_concurrent_budget_consumption_is_atomic_and_durable(self):
        sessions = [await self.start() for _ in range(3)]
        results = await asyncio.gather(*(self.auth(session, consume=True) for session in sessions), return_exceptions=True)
        self.assertEqual(sum(not isinstance(result, BaseException) for result in results), 2)
        denied = [result for result in results if isinstance(result, HTTPException)]
        self.assertEqual(denied[0].status_code, 429)
        async with self.database.transaction() as connection:
            usage = await connection.scalar(select(WebsiteWidget.usage).where(WebsiteWidget.id == self.widget.id))
        self.assertEqual(usage["chat_day_count"], 2)
        response = await admin_widget(self.database, self.assistant.id)
        self.assertEqual(response.requests_today, 2)

    @async_test
    async def test_passages_need_issued_citation_and_current_document_assignment(self):
        session = await self.start()
        widget, saved = await self.auth(session)
        with self.assertRaises(HTTPException):
            await visitor_passage(self.database, widget, saved, self.chunks[0])
        from app.schemas.chat import ChatSource
        await remember_sources(self.database, session["session_id"], [ChatSource(document_id=self.documents[0], chunk_id=self.chunks[0], filename="fixture.pdf", page_number=1)])
        widget, saved = await self.auth(session)
        self.assertEqual((await visitor_passage(self.database, widget, saved, self.chunks[0]))["content"], "Source evidence")
        with self.assertRaises(HTTPException):
            await visitor_passage(self.database, widget, saved, self.chunks[1])
        async with self.database.transaction() as connection:
            await connection.execute(delete(AssistantDocument).where(AssistantDocument.assistant_id == self.assistant.id))
        with self.assertRaises(HTTPException):
            await visitor_passage(self.database, widget, saved, self.chunks[0])

    @async_test
    async def test_session_issuance_is_bounded_and_disabled_assistant_fails_closed(self):
        async with self.database.transaction() as connection:
            now = await connection.scalar(select(func.now()))
            usage = {"sessions_minute": now.strftime("%Y-%m-%dT%H:%M"), "sessions_minute_count": 30}
            await connection.execute(update(WebsiteWidget).where(WebsiteWidget.id == self.widget.id).values(usage=usage))
        with self.assertRaises(HTTPException) as denied:
            await self.start()
        self.assertEqual(denied.exception.status_code, 429)
        with self.assertRaises(HTTPException):
            await admin_widget(self.database, self.assistant.id, self.payload.model_copy(update={"allowed_origins": []}))
        async with self.database.transaction() as connection:
            await connection.execute(update(Assistant).where(Assistant.id == self.assistant.id).values(active=False))
        with self.assertRaises(HTTPException) as disabled:
            await widget_page(self.database, self.widget.id, "https://shop.example.com")
        self.assertEqual(disabled.exception.status_code, 404)

    @async_test
    async def test_complete_http_flow_persists_memory_enforces_scope_and_reads_issued_sources(self):
        from app.api.v1.widgets import router, page_router
        from app.core.middleware import LocalWorkspaceMiddleware
        from app.schemas.chat import ChatResponse, ChatSource
        from app.services.metrics import MetricsCollector
        await admin_widget(self.database, self.assistant.id, self.payload.model_copy(update={"requests_per_minute": 20, "requests_per_day": 30}))
        app = FastAPI()
        app.state.database = self.database
        app.state.metrics = MetricsCollector(self.database)
        app.include_router(router, prefix="/v1"); app.include_router(page_router)
        app.add_middleware(LocalWorkspaceMiddleware, state=app.state, max_active_requests=4,
            widget_public_enabled=True, widget_public_origin="https://chat.example.com")
        answer = AsyncMock(return_value=ChatResponse(answer="The policy says this. [1]", sources=[
            ChatSource(document_id=self.documents[0], chunk_id=self.chunks[0], filename="fixture.pdf", page_number=1)]))
        transport = httpx.ASGITransport(app, client=("198.51.100.10", 1234))
        with patch("app.services.conversations.answer_question", answer):
            async with httpx.AsyncClient(transport=transport, base_url="https://chat.example.com") as client:
                frame = await client.get(f"/widget/{self.widget.id}", params={"parent_origin": "https://shop.example.com"})
                self.assertEqual(frame.status_code, 200)
                self.assertIn("frame-ancestors https://shop.example.com", frame.headers["content-security-policy"])
                response = await client.post(f"/v1/widget/{self.widget.id}/sessions", json={"parent_origin": "https://shop.example.com"}, headers={"Origin": "https://chat.example.com"})
                self.assertEqual(response.status_code, 201)
                session = response.json()
                base = f"/v1/widget/{self.widget.id}/sessions/{session['session_id']}"
                headers = {"Origin": "https://chat.example.com", "X-Widget-Token": session["token"]}
                first = await client.post(base + "/chat", json={"question": "What is the policy?"}, headers=headers)
                self.assertEqual(first.status_code, 200)
                second = await client.post(base + "/chat", json={"question": "Explain that"}, headers=headers)
                self.assertEqual(second.status_code, 200)
                self.assertEqual(len(answer.await_args.kwargs["history"]), 1)
                denied = await client.post(base + "/chat", json={"question": "Other document", "document_ids": [str(self.documents[1])]}, headers=headers)
                self.assertEqual(denied.status_code, 403)
                source = await client.get(base + f"/passages/{self.chunks[0]}", headers=headers)
                self.assertEqual(source.status_code, 200)
                self.assertEqual(source.json()["content"], "Source evidence")
                denied = await client.get(base + f"/passages/{self.chunks[1]}", headers=headers)
                self.assertEqual(denied.status_code, 404)
        async with self.database.transaction() as connection:
            history = await connection.scalar(select(ChatConversation.history).where(ChatConversation.assistant_id == self.assistant.id))
        self.assertEqual(len(history), 2)
        self.assertEqual(answer.await_count, 2)
        measurement, _ = app.state.metrics.queue.get_nowait()
        self.assertEqual(measurement["endpoint"], "/v1/widget/chat")
        self.assertEqual(measurement["assistant_id"], self.assistant.id)
        self.assertNotIn("token", str(measurement))
