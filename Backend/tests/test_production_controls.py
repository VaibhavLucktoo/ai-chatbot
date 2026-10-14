"""Check parser isolation and model budgets without external dependencies."""
import asyncio
import multiprocessing
import os
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace
import httpx
from fastapi import FastAPI, Request

from app.providers.documents import PDFExtractionError
from app.providers.pdf_process import extract_pdf_isolated
from app.services import llm
from app.core.middleware import LocalWorkspaceMiddleware
from tests.helpers import AsyncTestCase, async_test, make_pdf


class ParserIsolationTests(AsyncTestCase):
    @async_test
    async def test_extracts_text_in_separate_process(self):
        result = await extract_pdf_isolated(make_pdf("Retained source", None, "Page three"))
        self.assertEqual(result.page_count, 3)
        self.assertEqual([(p.page_number, p.text) for p in result.pages],
                         [(1, "Retained source"), (3, "Page three")])

    @async_test
    async def test_deadline_reaps_parser_process(self):
        before = {p.pid for p in multiprocessing.active_children()}
        with self.assertRaises(PDFExtractionError):
            await extract_pdf_isolated(make_pdf("Text"), timeout_seconds=0.001)
        self.assertEqual({p.pid for p in multiprocessing.active_children()}, before)

    @async_test
    async def test_cancellation_reaps_parser_process(self):
        before = {p.pid for p in multiprocessing.active_children()}
        task = asyncio.create_task(extract_pdf_isolated(make_pdf("Text")))
        await asyncio.sleep(0.001)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual({p.pid for p in multiprocessing.active_children()}, before)


class ContextBudgetTests(AsyncTestCase):
    @async_test
    async def test_input_and_output_must_fit_before_network_call(self):
        with patch.dict(llm._LLMSettings.model_config, {"env_file": None}), patch.dict(
            os.environ, {"RAG_CONTEXT_WINDOW_TOKENS": "4096", "LLM_MAX_OUTPUT_TOKENS": "2048"},
        ), patch.object(llm.httpx, "AsyncClient") as client:
            with self.assertRaisesRegex(llm.LLMResponseError, "context window"):
                await llm._generate_completion([{"role": "user", "content": "a" * 2000}])
            client.assert_not_called()


class BoundaryTests(AsyncTestCase):
    def application(self, blocked=None):
        app = FastAPI()
        app.add_middleware(LocalWorkspaceMiddleware, state=SimpleNamespace(), max_active_requests=1)

        @app.post("/echo")
        async def echo(request: Request):
            if blocked is not None:
                blocked[0].set()
                await blocked[1].wait()
            return {"length": len(await request.body())}
        return app

    @async_test
    async def test_remote_client_and_cross_origin_are_denied(self):
        app = self.application()
        for client_address, headers in ((('198.51.100.1', 5000), {}),
                                        (('127.0.0.1', 5000), {'Origin': 'https://example.com'})):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=client_address),
                                         base_url='http://127.0.0.1') as client:
                response = await client.post('/echo', headers=headers)
            self.assertEqual(response.status_code, 403)

    @async_test
    async def test_chunked_body_is_bounded_without_content_length(self):
        async def stream():
            yield b'a' * 20000
            yield b'b' * 20000
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.application()),
                                     base_url='http://127.0.0.1') as client:
            response = await client.post('/echo', content=stream())
        self.assertEqual(response.status_code, 413)

    @async_test
    async def test_concurrent_capacity_returns_429_and_recovers(self):
        started, release = asyncio.Event(), asyncio.Event()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.application((started, release))),
                                     base_url='http://127.0.0.1') as client:
            first = asyncio.create_task(client.post('/echo'))
            await asyncio.wait_for(started.wait(), 5)
            try:
                busy = await client.post('/echo')
                self.assertEqual(busy.status_code, 429)
            finally:
                release.set()
                self.assertEqual((await first).status_code, 200)
            self.assertEqual((await client.post('/echo')).status_code, 200)
