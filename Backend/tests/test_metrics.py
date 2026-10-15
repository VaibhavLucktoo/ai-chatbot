"""Measure real instrumented calls with mocked transport, without storing content."""
import asyncio
import json
import os
from dataclasses import asdict
from decimal import Decimal
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch
import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.v1.metrics import router
from app.core.config import ModelPrice
from app.core.middleware import LocalWorkspaceMiddleware
from app.schemas.chat import ChatRequest
from app.services import llm, rag
from app.services.metrics import MetricsCollector, record_graph, safe_usage
from tests.test_conversation import previous_turn
from tests.test_llm import completion
from tests.test_rag_service import stored_chunk


def collector():
    settings = SimpleNamespace(metrics_queue_capacity=10, metrics_write_timeout_seconds=0.05,
                               metrics_model_prices={"test-model": ModelPrice(input_usd_per_million=2, output_usd_per_million=4)})
    return MetricsCollector(SimpleNamespace(settings=settings))


class MetricsTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.enterContext(patch.dict(llm._LLMSettings.model_config, {"env_file": None}))
        self.enterContext(patch.dict(os.environ, {"LLM_MODEL": "test-model", "LLM_BASE_URL": "https://provider.example/v1", "LLM_API_KEY": "PRIVATE_KEY"}))

    async def test_capture_usage_cost_and_latency_without_sensitive_content(self):
        metrics = collector()
        response = completion("PRIVATE_ANSWER") | {"usage": {"prompt_tokens": 1000, "completion_tokens": 100, "total_tokens": 1100}}
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=response))) as client:
            with metrics.request("/v1/chat") as measurement, llm.llm_request_resources(client, asyncio.Semaphore(2)):
                self.assertEqual(await llm.generate_llm_response("PRIVATE_QUESTION"), "PRIVATE_ANSWER")
                measurement.http_status = 200
                record_graph({"intent": "document_question", "retrieval_performed": True, "result_count": 3,
                              "total_ms": 20, "timings_ms": {"retrieve": 5, "PRIVATE_KEY": 99},
                              "response": {"answer": "PRIVATE_ANSWER", "sources": [{"content": "PRIVATE_PASSAGE"}]},
                              "request": {"question": "PRIVATE_QUESTION", "conversation_id": "PRIVATE_SESSION"}}, prompt_version="abc")
        request, calls = metrics.queue.get_nowait()
        self.assertEqual(calls[0]["input_tokens"], 1000)
        self.assertEqual(calls[0]["estimated_cost_usd"], Decimal("0.0024"))
        self.assertGreaterEqual(calls[0]["duration_ms"], calls[0]["provider_ms"])
        self.assertEqual(request["stage_timings_ms"], {"retrieve": 5})
        self.assertEqual(request["source_count"], 1)
        self.assertNotIn("PRIVATE_", str((request, calls)))
        self.assertEqual(metrics.active_chats, 0)
        self.assertEqual(metrics.active_model_calls, 0)
        self.assertEqual(metrics.waiting_model_calls, 0)

    async def test_follow_up_answer_review_are_counted_once_each(self):
        metrics = collector()
        index = 0
        def handler(request):
            nonlocal index
            index += 1
            if index == 1:
                answer = '{"question":"How do I create and edit an event?","needs_clarification":false}'
            else:
                answer = '{"answer":"Open Events.","source_numbers":[1]}'
            return httpx.Response(200, json=completion(answer) | {"usage": {"prompt_tokens": 100 * index, "completion_tokens": 10 * index, "total_tokens": 110 * index}})
        chunk = asdict(stored_chunk(content="Open Events to create and edit an event."))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client, AsyncSession() as db:
            with metrics.request("/v1/chat") as measurement, llm.llm_request_resources(client, asyncio.Semaphore(2)), \
                 patch.object(rag, "search_similar_chunks", return_value=[chunk]):
                result = await rag.answer_question(db, ChatRequest(question="Explain that again."), history=(previous_turn(chunk["document_id"]),))
                measurement.http_status = 200
                self.assertTrue(result.sources)
        request, calls = metrics.queue.get_nowait()
        self.assertEqual([call["stage"] for call in calls], ["follow_up", "answer", "review"])
        self.assertEqual(sum(call["total_tokens"] for call in calls), 660)
        self.assertEqual(request["intent"], "follow_up")

    async def test_missing_malformed_usage_stays_unknown(self):
        self.assertEqual(safe_usage({"prompt_tokens": True, "completion_tokens": -1, "total_tokens": 3.1}), {"input_tokens": None, "output_tokens": None, "total_tokens": None})
        metrics = collector()
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=completion()))) as client:
            with metrics.request("/v1/chat") as measurement, llm.llm_request_resources(client, None):
                await llm.generate_llm_response("Question")
                measurement.http_status = 200
        _, calls = metrics.queue.get_nowait()
        self.assertIsNone(calls[0]["total_tokens"])
        self.assertIsNone(calls[0]["estimated_cost_usd"])

    async def test_rate_limit_and_cancelled_queue_preserve_gauges(self):
        metrics = collector()
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(429, text="PRIVATE_RESPONSE"))) as client:
            with metrics.request("/v1/chat") as measurement, llm.llm_request_resources(client, asyncio.Semaphore(1)):
                with self.assertRaises(llm.LLMRateLimitError):
                    await llm.generate_llm_response("Question")
                measurement.http_status = 429
            request, calls = metrics.queue.get_nowait()
            self.assertEqual(request["outcome"], "provider_rate_limit")
            self.assertEqual(calls[0]["error_type"], "LLMRateLimitError")
            slots = asyncio.Semaphore(0)
            async def queued():
                with metrics.request("/v1/chat"), llm.llm_request_resources(client, slots):
                    await llm.generate_llm_response("Question")
            task = asyncio.create_task(queued())
            for _ in range(100):
                if metrics.waiting_model_calls:
                    break
                await asyncio.sleep(0.001)
            self.assertEqual(metrics.waiting_model_calls, 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            request, calls = metrics.queue.get_nowait()
            self.assertEqual(request["outcome"], "cancelled")
            self.assertFalse(calls[0]["provider_requested"])
            self.assertIsNotNone(calls[0]["queue_ms"])
            self.assertEqual(metrics.waiting_model_calls, 0)
            self.assertEqual(metrics.active_chats, 0)

    async def test_simultaneous_requests_do_not_share_calls(self):
        metrics = collector()
        async def handler(request):
            await asyncio.sleep(0)
            question = json.loads(request.content)["messages"][0]["content"]
            return httpx.Response(200, json=completion(question) | {"usage": {"prompt_tokens": int(question), "completion_tokens": 1}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            async def run(question):
                with metrics.request("/v1/chat") as measurement, llm.llm_request_resources(client, None):
                    await llm.generate_llm_response(question)
                    measurement.http_status = 200
            await asyncio.gather(run("10"), run("20"))
        rows = [metrics.queue.get_nowait() for _ in range(2)]
        self.assertEqual(sorted(calls[0]["input_tokens"] for _, calls in rows), [10, 20])
        self.assertNotEqual(rows[0][0]["id"], rows[1][0]["id"])

    async def test_bounded_queue_and_writer_failure_do_not_fail_chat(self):
        metrics = collector()
        for _ in range(12):
            with metrics.request("/v1/chat") as measurement:
                measurement.http_status = 200
        self.assertEqual(metrics.queue.qsize(), 10)
        self.assertEqual(metrics.dropped_events, 2)
        with patch("app.storage.metrics.write_metrics", side_effect=OSError("PRIVATE_DATABASE_DETAILS")):
            metrics.start()
            with self.assertLogs("app.services.metrics", level="WARNING") as logs:
                await asyncio.wait_for(metrics.queue.join(), 2)
            await metrics.close()
        self.assertEqual(metrics.dropped_events, 12)
        self.assertNotIn("PRIVATE_DATABASE_DETAILS", str(logs.output))


class MetricsBoundaryTests(IsolatedAsyncioTestCase):
    def application(self):
        app = FastAPI()
        app.state.admin_token = "admin-token"
        app.state.metrics = collector()
        app.include_router(router, prefix="/v1")
        app.add_middleware(LocalWorkspaceMiddleware, state=app.state, max_active_requests=1)
        return app

    async def test_admin_boundary_and_malformed_token(self):
        app = self.application()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://127.0.0.1") as client:
            session = await client.get("/v1/admin/session")
            self.assertEqual(session.json(), {"token": "admin-token"})
            self.assertEqual(session.headers["Cache-Control"], "no-store")
            for headers in ({}, {"X-Admin-Token": "wrong"}, [(b"x-admin-token", b"\xff")]):
                response = await client.get("/v1/admin/metrics", headers=headers)
                self.assertEqual(response.status_code, 403)
            response = await client.get("/v1/admin/metrics?hours=721", headers={"X-Admin-Token": "admin-token"})
            self.assertEqual(response.status_code, 422)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app, client=("198.51.100.2", 5000)), base_url="http://127.0.0.1") as client:
            self.assertEqual((await client.get("/v1/admin/session")).status_code, 403)

    async def test_rejected_invalid_chat_is_recorded_and_analytics_does_not_count_itself(self):
        app = self.application()
        @app.post("/v1/chat")
        async def chat(request: ChatRequest):
            return {"answer": "Hello", "sources": []}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://127.0.0.1") as client:
            response = await client.post("/v1/chat", json={})
            self.assertEqual(response.status_code, 422)
            request, calls = app.state.metrics.queue.get_nowait()
            self.assertEqual(request["outcome"], "invalid_request")
            self.assertEqual(response.headers["X-Request-ID"], request["id"].hex)
            self.assertEqual(calls, [])
            await client.get("/v1/admin/session")
            self.assertEqual(app.state.metrics.queue.qsize(), 0)
