"""Widget origin, capability and isolation checks without real provider calls."""
import html
import json
import re
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from app.api.v1.chat import get_db_session
from app.api.v1.widgets import admin_router, page_router, router
from app.core.middleware import LocalWorkspaceMiddleware
from app.schemas.chat import ChatResponse
from app.schemas.widgets import WidgetWrite, website_origin
from app.services.widgets import budget
from app.core.config import get_settings
from app.widget_gateway import create_widget_gateway


class WidgetValidationTests(TestCase):
    def test_exact_origins_reject_wildcards_paths_credentials_and_csp_injection(self):
        self.assertEqual(website_origin("https://EXAMPLE.com:443/"), "https://example.com")
        self.assertEqual(website_origin("http://127.0.0.1:3001"), "http://127.0.0.1:3001")
        for origin in ("https://*.example.com", "http://example.com", "https://example.com/path", "https://a:b@example.com",
                       "https://example.com?x=1", "https://example.com/#x", "https://example.com;script-src", "null", "https://example.com\\evil"):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                website_origin(origin)
        with self.assertRaises(ValidationError):
            WidgetWrite(color="red; background:url(x)")

    def test_budgets_keep_daily_counts_and_reset_minute_window(self):
        now = datetime(2026, 10, 14, 10, 0, 15, tzinfo=timezone.utc)
        usage = budget({}, now, category="chat", minute_limit=1, day_limit=2)
        with self.assertRaises(HTTPException) as denied:
            budget(usage, now, category="chat", minute_limit=1, day_limit=2)
        self.assertEqual(denied.exception.status_code, 429)
        self.assertEqual(denied.exception.headers["Retry-After"], "45")
        later = now.replace(minute=1)
        usage = budget(usage, later, category="chat", minute_limit=1, day_limit=2)
        with self.assertRaises(HTTPException):
            budget(usage, later.replace(minute=2), category="chat", minute_limit=1, day_limit=2)
        self.assertEqual(budget(usage, later.replace(day=15), category="chat", minute_limit=1, day_limit=2)["chat_day_count"], 1)


class WidgetApiTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.widget_id, self.session_id, self.assistant_id = uuid4(), uuid4(), uuid4()
        self.token = "b" * 64
        self.app = FastAPI()
        self.app.include_router(router, prefix="/v1")
        self.app.include_router(admin_router, prefix="/v1")
        self.app.include_router(page_router)
        self.app.state.admin_token = "admin-test"
        self.app.state.database = SimpleNamespace()
        self.app.add_middleware(LocalWorkspaceMiddleware, state=self.app.state, max_active_requests=4,
            widget_public_enabled=True, widget_public_origin="https://chat.example.com")
        async def db():
            yield SimpleNamespace()
        self.app.dependency_overrides[get_db_session] = db
        self.widget = dict(id=self.widget_id, assistant_id=self.assistant_id, title='<img src=x onerror="alert(1)">',
            greeting="Welcome", color="#2563eb", position="right", revision=1, allowed_origins=["https://shop.example.com"])

    def remote_client(self, host="https://chat.example.com"):
        return httpx.AsyncClient(transport=httpx.ASGITransport(self.app, client=("198.51.100.10", 1234)), base_url=host)

    async def test_public_surface_never_exposes_admin_documents_or_workspace_chat(self):
        async with self.remote_client() as client:
            for method, path in (("GET", "/v1/admin/session"), ("GET", "/v1/assistants"), ("GET", "/v1/documents"),
                                 ("POST", "/v1/chat"), ("GET", "/admin"), ("GET", "/openapi.json"),
                                 ("GET", "/widget-assets/../admin/index.html")):
                with self.subTest(path=path):
                    self.assertEqual((await client.request(method, path)).status_code, 403)
            self.assertEqual((await client.get("/widget-assets/loader.js")).status_code, 200)
        async with self.remote_client("https://other.example.com") as client:
            self.assertEqual((await client.get("/widget-assets/loader.js")).status_code, 403)

    async def test_public_disabled_and_cross_origin_posts_fail_closed(self):
        path = f"/v1/widget/{self.widget_id}/sessions"
        with patch("app.api.v1.widget_visitor.start_visitor", AsyncMock()) as start:
            async with self.remote_client() as client:
                for origin in (None, "https://shop.example.com", "https://evil.example.com"):
                    response = await client.post(path, json={"parent_origin": "https://shop.example.com"}, headers={"Origin": origin} if origin else {})
                    self.assertEqual(response.status_code, 403)
            start.assert_not_awaited()
        app = FastAPI()
        app.add_middleware(LocalWorkspaceMiddleware, state=SimpleNamespace(), max_active_requests=1)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app, client=("198.51.100.10", 3)), base_url="https://chat.example.com") as client:
            self.assertEqual((await client.get("/widget-assets/loader.js")).status_code, 403)

    async def test_iframe_response_escapes_untrusted_titles_and_sets_exact_frame_policy(self):
        self.widget["title"] += " __TITLE__ __CONFIG__"
        with patch("app.api.v1.widget_assets.widget_page", AsyncMock(return_value=self.widget)):
            async with self.remote_client() as client:
                response = await client.get(f"/widget/{self.widget_id}", params={"parent_origin": "https://shop.example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('<img src=x', response.text)
        self.assertIn("&lt;img", response.text)
        self.assertIn("frame-ancestors https://shop.example.com;", response.headers["content-security-policy"])
        self.assertNotIn("unsafe-inline", response.headers["content-security-policy"])
        config = json.loads(html.unescape(re.search(r'data-config="([^"]*)"', response.text).group(1)))
        self.assertEqual(config["title"], self.widget["title"])

    async def test_chat_forces_assistant_and_server_conversation_and_rejects_extra_fields(self):
        conversation = uuid4()
        auth = AsyncMock(return_value=(self.widget, {"conversation_id": conversation}))
        run = AsyncMock(return_value=ChatResponse(answer="Hello", sources=[]))
        with patch("app.api.v1.widget_visitor.visitor", auth), patch("app.api.v1.widget_visitor.run_chat", run), patch("app.api.v1.widget_visitor.remember_sources", AsyncMock()):
            async with self.remote_client() as client:
                path = f"/v1/widget/{self.widget_id}/sessions/{self.session_id}/chat"
                headers = {"Origin": "https://chat.example.com", "X-Widget-Token": self.token}
                response = await client.post(path, json={"question": "Hello"}, headers=headers)
                self.assertEqual(response.status_code, 200)
                payload = run.await_args.args[1]
                self.assertEqual(payload.assistant_id, self.assistant_id)
                self.assertEqual(payload.conversation_id, conversation)
                self.assertEqual(run.await_args.kwargs["conversation_key"], self.token)
                for extra in ("assistant_id", "conversation_id", "top_k", "api_key"):
                    self.assertEqual((await client.post(path, json={"question": "Hello", extra: "private-value"}, headers=headers)).status_code, 422)
                self.assertEqual(run.await_count, 1)

    async def test_admin_settings_require_local_admin_token(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(self.app, client=("127.0.0.1", 4)), base_url="http://127.0.0.1") as client:
            path = f"/v1/admin/assistants/{self.assistant_id}/widget"
            self.assertEqual((await client.put(path, json={"enabled": True})).status_code, 403)
            with patch("app.api.v1.widget_admin.admin_widget", AsyncMock(return_value=None)):
                self.assertEqual((await client.get(path, headers={"X-Admin-Token": "admin-test"})).status_code, 200)

    async def test_dedicated_gateway_contains_no_admin_or_workspace_routes_even_on_loopback(self):
        settings = get_settings().model_copy(update={"widget_public_enabled": True, "widget_public_origin": "https://chat.example.com"})
        with patch("app.widget_gateway.get_settings", return_value=settings):
            gateway = create_widget_gateway()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(gateway, client=("127.0.0.1", 5)), base_url="http://127.0.0.1") as client:
            for path in ("/admin", "/v1/admin/session", "/v1/documents", "/v1/assistants", "/openapi.json", "/docs"):
                with self.subTest(path=path):
                    self.assertEqual((await client.get(path)).status_code, 404)

    async def test_gateway_startup_requires_explicit_enablement_and_https(self):
        for options in ({"widget_public_enabled": False, "widget_public_origin": "https://chat.example.com"},
                        {"widget_public_enabled": True, "widget_public_origin": "http://127.0.0.1:8000"}):
            with patch("app.widget_gateway.get_settings", return_value=get_settings().model_copy(update=options)):
                with self.assertRaises(RuntimeError):
                    create_widget_gateway()
