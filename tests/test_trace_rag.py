"""Local diagnostics preserve failure evidence without logging credentials."""

from contextlib import asynccontextmanager
from dataclasses import asdict
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.chat import ChatRequest
from app.services import rag
from app.services.llm import LLMResponseError
from scripts import trace_rag
from tests.test_rag_service import stored_chunk


class TraceTests(IsolatedAsyncioTestCase):
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
        self.assertEqual(len(result['messages']), 2)
        self.assertNotIn('response', result)
        closed.assert_awaited_once()

    async def test_trace_redacts_exception_details(self):
        with patch.object(trace_rag, 'get_settings', side_effect=RuntimeError('secret credentials')):
            result = await trace_rag.trace_question(ChatRequest(question='Where?'))
        self.assertEqual(result['error_type'], 'RuntimeError')
        self.assertNotIn('secret credentials', str(result))
