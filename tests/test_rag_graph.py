"""Check graph routing and isolation of simultaneous requests."""

import asyncio
import json
from dataclasses import asdict
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.chat import ChatRequest
from app.services import rag
from tests.test_rag_service import stored_chunk


class RAGGraphTests(IsolatedAsyncioTestCase):
    async def test_concurrent_answers_keep_state_and_sessions_separate(self):
        async def retrieve(db, question, top_k, document_ids):
            await asyncio.sleep(0)
            return [asdict(stored_chunk(filename=question + ".pdf", content=question))]

        async def generate(prompt, **kwargs):
            self.assertFalse(first.in_transaction())
            self.assertFalse(second.in_transaction())
            await asyncio.sleep(0)
            question = json.loads(prompt.split("QUESTION (JSON string):\n")[1].split("\n\nANSWER:")[0])
            return json.dumps({"answer": question, "source_numbers": [1]})

        first_trace, second_trace = {}, {}
        async with AsyncSession() as first, AsyncSession() as second:
            with patch.object(rag, "search_similar_chunks", side_effect=retrieve), \
                 patch.object(rag, "generate_llm_response", side_effect=generate), \
                 patch.object(rag, "get_settings", return_value=SimpleNamespace(
                     rag_max_context_chunks=5, rag_max_cosine_distance=0.45,
                 )):
                answers = await asyncio.gather(
                    rag.answer_question(first, ChatRequest(question="Alpha"), trace=first_trace),
                    rag.answer_question(second, ChatRequest(question="Beta"), trace=second_trace),
                )
        self.assertEqual([a.answer for a in answers], ["Alpha [1]", "Beta [1]"])
        self.assertEqual([a.sources[0].filename for a in answers], ["Alpha.pdf", "Beta.pdf"])
        for trace in (first_trace, second_trace):
            self.assertEqual(trace["workflow_steps"], [
                "retrieve", "select_context", "prepare_prompt", "generate", "validate",
            ])

    async def test_empty_retrieval_takes_fallback_branch(self):
        trace = {}
        async with AsyncSession() as session:
            with patch.object(rag, "search_similar_chunks", return_value=[]), \
                 patch.object(rag, "generate_llm_response") as generate, \
                 patch.object(rag, "get_settings", return_value=SimpleNamespace(
                     rag_max_context_chunks=5, rag_max_cosine_distance=0.45,
                 )):
                await rag.answer_question(session, ChatRequest(question="Missing answer?"), trace=trace)
        generate.assert_not_awaited()
        self.assertEqual(trace["workflow_steps"], ["retrieve", "select_context", "fallback"])
