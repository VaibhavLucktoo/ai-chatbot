"""Document selection must avoid generation and preserve the original question."""

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.chat import get_db_session
from app.api.v1.router import api_router
from app.schemas.chat import ChatRequest, ClarificationResponse
from app.services import rag


class DocumentClarificationTests(IsolatedAsyncioTestCase):
    async def test_ambiguous_question_returns_filename_choices_without_inference(self):
        # Duplicate filenames retain different IDs so a click stays unambiguous.
        rows = [SimpleNamespace(id=uuid4(), filename="policy.pdf") for _ in range(2)]
        db = AsyncMock(spec=AsyncSession)
        db.execute.return_value = Mock(all=Mock(return_value=rows))
        trace = {}
        with patch.object(rag, "search_similar_chunks", new_callable=AsyncMock) as search, \
             patch.object(rag, "generate_llm_response", new_callable=AsyncMock) as generate:
            response = await rag.answer_question(
                db, ChatRequest(question="Summarize this document", top_k=3), trace=trace,
            )
        self.assertIsInstance(response, ClarificationResponse)
        self.assertEqual(response.original_question, "Summarize this document")
        self.assertEqual(response.top_k, 3)
        self.assertEqual([d.document_id for d in response.documents], [r.id for r in rows])
        self.assertEqual(trace["response"]["status"], "clarification_required")
        search.assert_not_awaited()
        generate.assert_not_awaited()

    async def test_one_document_auto_selects_and_explicit_selection_skips_choices(self):
        document_id = uuid4()
        for selected in (None, [document_id]):
            db = AsyncMock(spec=AsyncSession)
            db.execute.return_value = Mock(all=Mock(return_value=[
                SimpleNamespace(id=document_id, filename="policy.pdf"),
            ]))
            with patch.object(rag, "search_similar_chunks", new_callable=AsyncMock, return_value=[]) as search, \
                 patch.object(rag, "get_settings", return_value=SimpleNamespace(
                     rag_max_context_chunks=5, rag_max_cosine_distance=0.5,
                 )):
                response = await rag.answer_question(db, ChatRequest(
                    question="Summarize this document", document_ids=selected,
                ))
            self.assertEqual(search.await_args.kwargs["document_ids"], [document_id])
            self.assertEqual(response.sources, [])
            if selected:
                db.execute.assert_not_awaited()

    async def test_no_documents_requests_upload(self):
        db = AsyncMock(spec=AsyncSession)
        db.execute.return_value = Mock(all=Mock(return_value=[]))
        with patch.object(rag, "search_similar_chunks", new_callable=AsyncMock) as search:
            response = await rag.answer_question(db, ChatRequest(question="Explain this PDF"))
        self.assertEqual(response.documents, [])
        self.assertIn("upload", response.question)
        search.assert_not_awaited()

    async def test_api_serializes_clarification(self):
        app = FastAPI()
        app.include_router(api_router, prefix="/v1")

        async def session():
            yield AsyncMock(spec=AsyncSession)

        app.dependency_overrides[get_db_session] = session
        response = ClarificationResponse(
            question="Which document?", original_question="Summarize it",
            top_k=5, documents=[],
        )
        with patch("app.api.v1.chat.answer_question", new_callable=AsyncMock, return_value=response):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test",
            ) as client:
                result = await client.post("/v1/chat", json={"question": "Summarize it"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), response.model_dump(mode="json"))

    def test_specific_questions_keep_cross_document_search(self):
        self.assertFalse(rag.needs_document_selection("What is the annual leave policy?"))
        self.assertTrue(rag.needs_document_selection("Summarize this PDF"))
