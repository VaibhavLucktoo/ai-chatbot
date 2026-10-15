"""Routing and prompt boundaries without external provider or database calls."""
import asyncio
import json
from dataclasses import asdict
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import rag, conversation_intent, conversations
from app.services.conversation_intent import Turn, detect_intent
from app.services.llm import LLMResponseError, LLMTimeoutError
from app.storage.conversations import ConversationClaim, bounded_history
from tests.test_rag_service import stored_chunk


def previous_turn(identifier=None, **changes):
    return Turn(**(dict(question="How do I create an event?", resolved_question="How do I create an event?",
                        answer="1. Open Events. 2. Select Create.",
                        document_ids=(str(identifier),) if identifier else None,
                        intent="document_question", grounded=True) | changes))


class IntentTests(TestCase):
    def test_mixed_greetings_and_unknown_topics_remain_document_questions(self):
        for question in ("Hello, what is the leave policy?", "How are you handling probation?",
                         "What is the Mars mission budget?", "Explain this PDF"):
            self.assertEqual(detect_intent(question), "document_question")

    def test_bounded_memory_keeps_complete_recent_turns(self):
        turns = [previous_turn(question=str(index)) for index in range(10)]
        self.assertEqual([item["question"] for item in bounded_history(turns, max_turns=3, max_bytes=12000)], ["7", "8", "9"])
        self.assertEqual(bounded_history([previous_turn(answer="x" * 2000)], max_turns=6, max_bytes=1000), [])
        bounded = bounded_history([previous_turn(answer="é" * 200) for _ in range(8)], max_turns=6, max_bytes=1600)
        self.assertLessEqual(len(json.dumps(bounded, ensure_ascii=False).encode("utf-8")), 1600)


class ConversationGraphTests(IsolatedAsyncioTestCase):
    async def test_greetings_casual_messages_and_actions_skip_all_provider_work(self):
        for question, expected in (("Hello!", "conversation"), ("How are you?", "conversation"),
                                   ("Thank you", "conversation"), ("Okay", "conversation"),
                                   ("Send an email to my manager", "unsupported")):
            with self.subTest(question=question), patch.object(rag, "search_similar_chunks") as retrieve, \
                 patch.object(rag, "generate_llm_response") as generate, \
                 patch.object(conversation_intent, "generate_llm_response") as resolve:
                trace = {}
                async with AsyncSession() as db:
                    response = await rag.answer_question(db, ChatRequest(question=question), trace=trace)
                self.assertIsInstance(response, ChatResponse)
                self.assertEqual(response.sources, [])
                self.assertNotEqual(response.answer, rag.INSUFFICIENT_CONTEXT_ANSWER)
                self.assertEqual(trace["intent"], expected)
                self.assertFalse(trace["retrieval_performed"])
                self.assertEqual(trace["workflow_steps"], ["route_intent"])
                retrieve.assert_not_awaited()
                generate.assert_not_awaited()
                resolve.assert_not_awaited()

    async def test_follow_up_retrieves_fresh_evidence_and_preserves_explicit_scope(self):
        old_id, new_id = uuid4(), uuid4()
        prior = previous_turn(old_id, answer="OLD UNVERIFIED CLAIM: Create is second.")
        chunk = asdict(stored_chunk(content="Select Create in Events."))
        chunk["document_id"] = new_id
        rewrite = json.dumps({"question": "How do I select Create in Events?", "needs_clarification": False})
        trace = {}
        with patch.object(conversation_intent, "generate_llm_response", return_value=rewrite) as resolver, \
             patch.object(rag, "search_similar_chunks", return_value=[chunk]) as retrieve, \
             patch.object(rag, "generate_llm_response", return_value=json.dumps({"answer": "Select Create in Events.", "source_numbers": [1]})) as generate:
            async with AsyncSession() as db:
                request = ChatRequest(question="Explain the second step again.", top_k=3, document_ids=[new_id])
                response = await rag.answer_question(db, request, history=(prior,), trace=trace)
            retrieve.assert_awaited_once_with(db=db, question="How do I select Create in Events?", top_k=3, document_ids=[new_id])
            self.assertEqual(response.sources[0].document_id, new_id)
            self.assertIn("OLD UNVERIFIED CLAIM", resolver.await_args.args[0])
            self.assertNotIn("OLD UNVERIFIED CLAIM", generate.await_args.args[0])
            self.assertEqual(generate.await_args.kwargs["system_prompt"], rag.RAG_SYSTEM_PROMPT)
            self.assertEqual(trace["intent"], "follow_up")

    async def test_implicit_follow_up_inherits_previous_scope_and_can_decline_reference(self):
        identifier = uuid4()
        with patch.object(conversation_intent, "generate_llm_response", return_value=json.dumps({"question": "What is event creation step two?", "needs_clarification": False})), \
             patch.object(rag, "search_similar_chunks", return_value=[]) as retrieve:
            async with AsyncSession() as db:
                response = await rag.answer_question(db, ChatRequest(question="Explain the second step again."), history=(previous_turn(identifier),))
            self.assertEqual(retrieve.await_args.kwargs["document_ids"], [identifier])
            self.assertEqual(response.answer, rag.INSUFFICIENT_CONTEXT_ANSWER)
        with patch.object(conversation_intent, "generate_llm_response", return_value='{"question":null,"needs_clarification":true}'), \
             patch.object(rag, "search_similar_chunks") as retrieve:
            async with AsyncSession() as db:
                response = await rag.answer_question(db, ChatRequest(question="Explain the second step again."), history=(previous_turn(identifier),))
            self.assertEqual(response.answer, conversation_intent.FOLLOW_UP_CLARIFICATION)
            retrieve.assert_not_awaited()

    async def test_missing_or_ungrounded_reference_never_reuses_model_claims(self):
        for history in ((), (previous_turn(grounded=False),),
                        (previous_turn(), previous_turn(intent="unsupported", grounded=False))):
            with patch.object(conversation_intent, "generate_llm_response") as resolve, \
                 patch.object(rag, "search_similar_chunks") as retrieve:
                async with AsyncSession() as db:
                    response = await rag.answer_question(db, ChatRequest(question="Explain the second step again."), history=history)
                self.assertEqual(response.sources, [])
                self.assertEqual(response.answer, conversation_intent.FOLLOW_UP_CLARIFICATION)
                resolve.assert_not_awaited()
                retrieve.assert_not_awaited()

    async def test_invalid_resolver_output_fails_closed_before_retrieval(self):
        for answer in ("plain prose", '{"question":"x","needs_clarification":false,"document_ids":["attacker"]}',
                       '{"question":null,"needs_clarification":false}',
                       json.dumps({"question": "x" * 501, "needs_clarification": False})):
            with patch.object(conversation_intent, "generate_llm_response", return_value=answer), \
                 patch.object(rag, "search_similar_chunks") as retrieve:
                async with AsyncSession() as db:
                    with self.assertRaises(LLMResponseError):
                        await rag.answer_question(db, ChatRequest(question="Explain the second step again."), history=(previous_turn(),))
                retrieve.assert_not_awaited()

    async def test_provider_timeout_propagates_from_resolution(self):
        with patch.object(conversation_intent, "generate_llm_response", side_effect=LLMTimeoutError("private")), \
             patch.object(rag, "search_similar_chunks") as retrieve:
            async with AsyncSession() as db:
                with self.assertRaises(LLMTimeoutError):
                    await rag.answer_question(db, ChatRequest(question="Explain the second step again."), history=(previous_turn(),))
            retrieve.assert_not_awaited()

    async def test_safe_metrics_exclude_questions_history_and_sources(self):
        with patch.object(rag, "search_similar_chunks", return_value=[]):
            with self.assertLogs("app.services.rag", level="INFO") as logs:
                async with AsyncSession() as db:
                    await rag.answer_question(db, ChatRequest(question="PRIVATE SENTINEL QUESTION"))
        text = "\n".join(logs.output)
        self.assertNotIn("PRIVATE SENTINEL", text)
        for field in ("intent", "retrieval_performed", "result_count", "timings_ms", "token_usage", "insufficient_evidence"):
            self.assertIn(field, text)


class ConversationServiceTests(IsolatedAsyncioTestCase):
    async def test_failures_and_cancellation_release_claim_without_saving_an_answer(self):
        request = ChatRequest(question="Question", conversation_id=uuid4())
        claim = ConversationClaim(request.conversation_id, uuid4(), ())
        for error in (LLMTimeoutError("private"), asyncio.CancelledError()):
            with patch.object(conversations, "claim_conversation", return_value=claim), \
                 patch.object(conversations, "answer_question", side_effect=error), \
                 patch.object(conversations, "finish_conversation") as finish, \
                 patch.object(conversations, "release_conversation") as release:
                with self.assertRaises(type(error)):
                    await conversations.answer_conversation(object(), object(), request, "a" * 64)
                finish.assert_not_awaited()
                release.assert_awaited_once()
