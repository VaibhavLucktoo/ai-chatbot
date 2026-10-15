"""Local diagnostics preserve failure evidence without logging credentials."""

from contextlib import asynccontextmanager
from dataclasses import asdict
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.chat import ChatRequest
from app.services import rag
from app.services.llm import LLMResponseError
from app.services.llm import effective_model_settings
from scripts import trace_rag
from tests.test_rag_service import stored_chunk


class TraceTests(IsolatedAsyncioTestCase):
    async def test_trace_uses_selected_assistant_scope_model_and_lease(self):
        assistant = SimpleNamespace(id=uuid4(), revision=7, document_ids=(uuid4(),), model_settings=object())
        database = SimpleNamespace(close=AsyncMock())
        active = False

        @asynccontextmanager
        async def session():
            yield object()

        @asynccontextmanager
        async def lease(db, identifier):
            nonlocal active
            self.assertIs(db, database)
            self.assertEqual(identifier, assistant.id)
            active = True
            try:
                yield
            finally:
                active = False

        async def answer(db, request, *, trace, assistant):
            self.assertTrue(active)
            self.assertIs(effective_model_settings(), assistant.model_settings)
            self.assertEqual(assistant.document_ids, selected.document_ids)
            raise LLMResponseError('private provider details')

        selected = assistant
        database.session = session
        request = ChatRequest(question='Where?', assistant_id=assistant.id, document_ids=list(assistant.document_ids))
        with (
            patch.object(trace_rag, 'get_settings', return_value=SimpleNamespace(embedding_model='test')),
            patch.object(trace_rag, 'Database', return_value=database),
            patch.object(trace_rag, 'load_assistant_runtime', new_callable=AsyncMock, return_value=assistant) as load,
            patch.object(trace_rag, 'stateless_assistant_turn', lease),
            patch.object(trace_rag, 'answer_question', side_effect=answer),
        ):
            result = await trace_rag.trace_question(request)
        load.assert_awaited_once_with(database, assistant.id, request.document_ids)
        self.assertFalse(active)
        self.assertEqual(result['error_type'], 'LLMResponseError')
        self.assertEqual(result['assistant_revision'], 7)
        self.assertNotIn('private provider details', str(result))
        database.close.assert_awaited_once()

    async def test_failed_answer_retains_passages_prompt_and_raw_output(self):
        closed = AsyncMock()

        @asynccontextmanager
        async def session():
            async with AsyncSession() as db:
                yield db

        database = SimpleNamespace(session=session, close=closed)
        chunk = asdict(stored_chunk())
        with (
            patch.object(trace_rag, 'Database', return_value=database),
            patch.object(trace_rag, 'get_settings', return_value=SimpleNamespace(embedding_model='test')),
            patch.object(rag, 'search_similar_chunks', return_value=[chunk]),
            patch.object(rag, 'generate_llm_response', return_value='Invented answer without citations'),
        ):
            result = await trace_rag.trace_question(ChatRequest(question='Where?'))
        self.assertEqual(result['error_type'], LLMResponseError.__name__)
        self.assertEqual(result['raw_answer'], 'Invented answer without citations')
        self.assertEqual(result['retrieved_chunks'], [chunk])
        self.assertEqual(result['selected_chunks'], [chunk])
        self.assertEqual(result['rag_max_context_chunks'], 5)
        self.assertTrue(result['sufficient_evidence'])
        self.assertEqual(len(result['messages']), 2)
        self.assertNotIn('response', result)
        closed.assert_awaited_once()

    async def test_trace_redacts_exception_details(self):
        with patch.object(trace_rag, 'get_settings', side_effect=RuntimeError('secret credentials')):
            result = await trace_rag.trace_question(ChatRequest(question='Where?'))
        self.assertEqual(result['error_type'], 'RuntimeError')
        self.assertNotIn('secret credentials', str(result))
