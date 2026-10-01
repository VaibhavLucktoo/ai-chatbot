"""Chat endpoint behavior without a live database or LLM server."""

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import asdict
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.chat import get_db_session
from app.api.v1.router import api_router
from app.schemas.chat import ChatRequest, ChatResponse, ChatSource
from app.services.llm import (
    LLMConnectionError, LLMError, LLMRateLimitError,
    LLMResponseError, LLMTimeoutError,
)
from app.services.rag import INSUFFICIENT_CONTEXT_ANSWER
from app.services.retrieval import RetrievalProviderError
from app.storage.documents import StoredChunkResult


class ChatApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.app = FastAPI()
        self.app.include_router(api_router, prefix="/v1")
        self.db = AsyncMock(spec=AsyncSession)

        async def override_session():
            yield self.db

        self.app.dependency_overrides[get_db_session] = override_session

    def client(self, app=None, raise_app_exceptions=True):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=app or self.app, raise_app_exceptions=raise_app_exceptions,
            ),
            base_url="http://test",
        )

    async def test_success_uses_injected_session_and_serializes_sources(self):
        source = ChatSource(document_id=uuid4(), chunk_id=uuid4(), filename="report.pdf", page_number=2)
        result = ChatResponse(answer="The answer. [1]", sources=[source])
        with patch("app.api.v1.chat.answer_question", return_value=result) as answer:
            async with self.client() as client:
                response = await client.post("/v1/chat", json={"question": "  Question  ", "top_k": 3})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), result.model_dump(mode="json"))
        answer.assert_awaited_once_with(self.db, ChatRequest(question="Question", top_k=3))

    async def test_invalid_payloads_remain_http_422(self):
        payloads = ({}, {"question": ""}, {"question": "  "}, {"question": 123},
                    {"question": "x" * 501}, {"question": "Q", "top_k": 0},
                    {"question": "Q", "top_k": 21}, {"question": "Q", "top_k": True},
                    {"question": "Q", "extra": "invalid"}, [])
        with patch("app.api.v1.chat.answer_question") as answer:
            async with self.client() as client:
                for payload in payloads:
                    with self.subTest(payload=payload):
                        response = await client.post("/v1/chat", json=payload)
                        self.assertEqual(response.status_code, 422)
                response = await client.post("/v1/chat", content="{", headers={"Content-Type": "application/json"})
                self.assertEqual(response.status_code, 422)
            answer.assert_not_awaited()

    async def test_error_statuses_do_not_expose_private_exception_details(self):
        private = "private prompt, provider token, or database credentials"
        cases = (
            (RetrievalProviderError(private), 500), (SQLAlchemyError(private), 500),
            (TimeoutError(private), 500), (OSError(private), 500),
            (LLMTimeoutError(private), 504), (LLMConnectionError(private), 503),
            (LLMRateLimitError(private), 429), (LLMError(private), 502),
            (LLMResponseError(private), 502), (LLMResponseError(private, status_code=401), 502),
            (LLMResponseError(private, status_code=408), 504),
            (LLMResponseError(private, status_code=429), 429),
            (LLMResponseError(private, status_code=503), 503),
            (LLMResponseError(private, status_code=504), 504), (RuntimeError(private), 500),
        )
        async with self.client() as client:
            for error, expected_status in cases:
                with self.subTest(error=type(error).__name__, status=getattr(error, "status_code", None)):
                    with patch("app.api.v1.chat.answer_question", side_effect=error):
                        with self.assertLogs("app.api.v1.chat", level="WARNING") as logs:
                            response = await client.post("/v1/chat", json={"question": "Question"})
                    self.assertEqual(response.status_code, expected_status)
                    self.assertIsInstance(response.json()["detail"], str)
                    self.assertNotIn(private, response.text)
                    self.assertNotIn(private, "\n".join(logs.output))

    async def test_internal_validation_errors_are_http_500(self):
        try:
            ChatResponse(answer=None, sources=[])
        except ValidationError as error:
            failure = error
        with patch("app.api.v1.chat.answer_question", side_effect=failure):
            async with self.client() as client:
                response = await client.post("/v1/chat", json={"question": "Question"})
        self.assertEqual(response.status_code, 500)

    async def test_http_exceptions_preserve_their_status(self):
        with patch("app.api.v1.chat.answer_question", side_effect=HTTPException(status_code=409, detail="Conflict")):
            async with self.client() as client:
                response = await client.post("/v1/chat", json={"question": "Question"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": "Conflict"})

    async def test_empty_retrieval_uses_real_rag_fallback_without_llm(self):
        with (
            patch("app.services.rag.search_similar_chunks", return_value=[]) as search,
            patch("app.services.rag.generate_llm_response") as generate,
        ):
            async with self.client() as client:
                response = await client.post("/v1/chat", json={"question": "Question"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"answer": INSUFFICIENT_CONTEXT_ANSWER, "sources": []})
        search.assert_awaited_once_with(db=self.db, question="Question", top_k=5, document_ids=None)
        generate.assert_not_awaited()

    async def test_real_rag_service_returns_generated_answer_and_sources(self):
        chunk = StoredChunkResult(uuid4(), uuid4(), "report.pdf", 3, 0, "Vectors are in PostgreSQL.", 0.1)
        with (
            patch("app.services.rag.search_similar_chunks", return_value=[asdict(chunk)]),
            patch("app.services.rag.generate_llm_response", return_value=json.dumps({
                'answer': 'In PostgreSQL.', 'source_numbers': [1],
            })) as generate,
        ):
            async with self.client() as client:
                response = await client.post("/v1/chat", json={"question": "Where are vectors stored?"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "In PostgreSQL. [1]")
        self.assertEqual(response.json()["sources"], [{
            "document_id": str(chunk.document_id), "chunk_id": str(chunk.chunk_id),
            "filename": "report.pdf", "page_number": 3,
        }])
        generate.assert_awaited_once()
        self.assertIn(chunk.content, generate.await_args.args[0])

    async def test_missing_application_database_is_http_500(self):
        self.app.dependency_overrides.clear()
        with patch("app.api.v1.chat.answer_question") as answer:
            async with self.client() as client:
                response = await client.post("/v1/chat", json={"question": "Question"})
        self.assertEqual(response.status_code, 500)
        answer.assert_not_awaited()

    async def test_real_rag_rejects_fabricated_citations_with_502(self):
        chunk = StoredChunkResult(uuid4(), uuid4(), "policy.pdf", 11, 0, "Policy text.", 0.1)
        with (
            patch("app.services.rag.search_similar_chunks", return_value=[asdict(chunk)]),
            patch("app.services.rag.generate_llm_response", return_value=json.dumps({
                'answer': 'Unsupported claim', 'source_numbers': [99],
            })),
        ):
            async with self.client() as client:
                response = await client.post("/v1/chat", json={"question": "Policy?"})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("Unsupported claim", response.text)

    async def test_nonempty_context_fallback_has_no_sources(self):
        chunk = StoredChunkResult(uuid4(), uuid4(), "manual.pdf", 1, 0, "Unrelated text.", 0.8)
        with (
            patch("app.services.rag.search_similar_chunks", return_value=[asdict(chunk)]),
            patch("app.services.rag.generate_llm_response", return_value=json.dumps({
                'answer': INSUFFICIENT_CONTEXT_ANSWER, 'source_numbers': [],
            })),
        ):
            async with self.client() as client:
                response = await client.post("/v1/chat", json={"question": "Policy?"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"answer": INSUFFICIENT_CONTEXT_ANSWER, "sources": []})

    async def test_dependency_setup_and_cleanup_errors_are_http_500(self):
        self.app.dependency_overrides.clear()
        for stage in ("__aenter__", "__aexit__"):
            with self.subTest(stage=stage):
                context = AsyncMock()
                context.__aenter__.return_value = self.db
                context.__aexit__.return_value = False
                getattr(context, stage).side_effect = SQLAlchemyError("private database credentials")
                self.app.state.database = SimpleNamespace(session=Mock(return_value=context))
                with patch("app.api.v1.chat.answer_question", return_value=ChatResponse(answer="Answer", sources=[])) as answer:
                    async with self.client() as client:
                        response = await client.post("/v1/chat", json={"question": "Question"})
                self.assertEqual(response.status_code, 500)
                self.assertNotIn("private database credentials", response.text)
                if stage == "__aenter__":
                    answer.assert_not_awaited()

    async def test_session_cleanup_precedes_response_and_runs_after_failures(self):
        self.app.dependency_overrides.clear()
        for failure, expected_status in ((None, 200), (LLMTimeoutError("Timed out"), 504)):
            events = []

            @asynccontextmanager
            async def session_context():
                events.append("opened")
                try:
                    yield self.db
                finally:
                    events.append("closed")

            async def observed_app(scope, receive, send):
                async def observe_send(message):
                    if message["type"] == "http.response.start":
                        self.assertEqual(events, ["opened", "closed"])
                    await send(message)
                await self.app(scope, receive, observe_send)

            self.app.state.database = SimpleNamespace(session=session_context)
            with self.subTest(status=expected_status):
                with patch("app.api.v1.chat.answer_question", side_effect=failure, return_value=ChatResponse(answer="Answer", sources=[])):
                    async with self.client(app=observed_app) as client:
                        response = await client.post("/v1/chat", json={"question": "Question"})
                self.assertEqual(response.status_code, expected_status)
                self.assertEqual(events, ["opened", "closed"])

    async def test_cancellation_propagates_and_closes_session(self):
        self.app.dependency_overrides.clear()
        closed = []

        @asynccontextmanager
        async def session_context():
            try:
                yield self.db
            finally:
                closed.append(True)

        self.app.state.database = SimpleNamespace(session=session_context)
        with patch("app.api.v1.chat.answer_question", side_effect=asyncio.CancelledError):
            async with self.client() as client:
                with self.assertRaises(asyncio.CancelledError):
                    await client.post("/v1/chat", json={"question": "Question"})
        self.assertEqual(closed, [True])

    async def test_database_session_factory_uses_existing_engine_and_closes(self):
        from app.core.config import get_settings
        from app.storage.db import Database

        database = Database(get_settings())
        try:
            context = database.session()
            session = await context.__aenter__()
            self.assertIsInstance(session, AsyncSession)
            self.assertFalse(session.autoflush)
            self.assertFalse(session.sync_session.expire_on_commit)
            with patch.object(session, "close", wraps=session.close) as close:
                await context.__aexit__(None, None, None)
                close.assert_awaited_once()
        finally:
            await database.close()

    async def test_openapi_documents_response_codes_and_request_body(self):
        async with self.client() as client:
            response = await client.get("/openapi.json")
        schema = response.json()
        operation = schema["paths"]["/v1/chat"]["post"]
        for code in ("200", "422", "429", "500", "502", "503", "504"):
            self.assertIn(code, operation["responses"])
        self.assertEqual(operation["requestBody"]["content"]["application/json"]["schema"]["$ref"], "#/components/schemas/ChatRequest")
        self.assertEqual(operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"], "#/components/schemas/ChatResponse")
