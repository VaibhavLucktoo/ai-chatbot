"""Protect wire contracts, dependency identity and serialization during moves."""

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import APIRouter, FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
import httpx
from sqlalchemy.exc import SQLAlchemyError

from app.api.common.routes import ConfigurationRoute, WidgetConfigurationRoute
from app.api.dependencies import get_db_session
from app.api.v1 import (
    admin,
    chat,
    document_catalog,
    widgets,
    widget_admin,
    widget_assets,
    widget_visitor,
)
from app.core.config import get_settings
from app.main import create_app
from app.services import assistants, chat_service, provider_service
from app.storage import document_catalog as catalog_storage
from app.widget_gateway import create_widget_gateway
from scripts.check_api_contract import check_contract


class RefactorContractTests(TestCase):
    def test_openapi_matches_pre_refactor_wire_contract(self):
        baseline = (
            Path(__file__).parent / "fixtures" / "api_contract_before_refactor.json"
        )
        count, unique = check_contract(
            json.loads(baseline.read_text(encoding="utf-8")),
            create_app().openapi(),
            documentation_updates=True,
        )
        self.assertEqual((count, unique), (39, 39))

    def test_compatibility_exports_preserve_callable_identity(self):
        self.assertIs(chat.get_db_session, get_db_session)
        self.assertIs(chat.run_chat, chat_service.run_chat)
        self.assertIs(document_catalog.metadata_query, catalog_storage.metadata_query)
        for name in (
            "delete_connection",
            "list_connections",
            "save_connection",
            "connection_credentials",
        ):
            self.assertIs(getattr(assistants, name), getattr(provider_service, name))
        for module, names in (
            (widget_admin, ("admin_router", "get_widget", "save_widget")),
            (widget_assets, ("page_router", "render_widget", "widget_asset")),
            (widget_visitor, ("router", "start", "widget_chat", "passage")),
        ):
            for name in names:
                self.assertIs(getattr(widgets, name), getattr(module, name))

    def test_gateway_exposes_exactly_the_existing_visitor_surface(self):
        settings = get_settings().model_copy(
            update={
                "widget_public_enabled": True,
                "widget_public_origin": "https://chat.example.com",
            }
        )
        with patch("app.widget_gateway.get_settings", return_value=settings):
            gateway = create_widget_gateway()
        routes = []
        for route in gateway.routes:
            routes.extend(
                route.effective_route_contexts()
                if hasattr(route, "effective_route_contexts")
                else [route]
            )
        actual = {
            (method, route.path) for route in routes for method in (route.methods or [])
        }
        self.assertEqual(
            actual,
            {
                ("GET", "/widget/{widget_id}"),
                ("GET", "/widget-assets/{filename}"),
                ("POST", "/v1/widget/{widget_id}/sessions"),
                ("POST", "/v1/widget/{widget_id}/sessions/{session_id}/chat"),
                (
                    "GET",
                    "/v1/widget/{widget_id}/sessions/{session_id}/passages/{chunk_id}",
                ),
            },
        )

    def test_json_success_responses_are_typed_and_tags_are_consistent(self):
        for path, item in create_app().openapi()["paths"].items():
            for operation in item.values():
                for tag in operation.get("tags", []):
                    self.assertEqual(tag, tag.lower())
                # Asset responses are JavaScript/CSS rather than JSON; retain their old docs.
                if path == "/widget-assets/{filename}":
                    continue
                for status, response in operation["responses"].items():
                    if status.startswith("2"):
                        content = response.get("content", {}).get("application/json")
                        if content is not None:
                            self.assertTrue(content.get("schema"), (path, status))


class RefactorSerializationTests(IsolatedAsyncioTestCase):
    async def test_admin_document_response_preserves_timestamp_and_null_fields(self):
        app = FastAPI()
        app.include_router(admin.router, prefix="/v1")
        app.state.admin_token = "test-admin-token"

        async def session():
            yield object()

        app.dependency_overrides[get_db_session] = session
        row = dict(
            id=uuid4(),
            filename="fixture.pdf",
            page_count=1,
            status="ready",
            created_at=datetime(2026, 10, 15, 9, 30, tzinfo=timezone.utc),
            active=True,
            processing_metadata=None,
            chunk_count=2,
            lease_active=None,
        )
        expected = jsonable_encoder(
            {
                "items": [{**row, "recoverable": False}],
                "total": 1,
                "limit": 25,
                "offset": 0,
            }
        )
        with patch(
            "app.api.v1.admin.read_admin_documents", AsyncMock(return_value=(1, [row]))
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://127.0.0.1"
            ) as client:
                response = await client.get(
                    "/v1/admin/documents", headers={"X-Admin-Token": "test-admin-token"}
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, JSONResponse(expected).body)
        self.assertEqual(
            response.json()["items"][0]["created_at"], "2026-10-15T09:30:00+00:00"
        )

    async def test_widget_passage_response_preserves_stored_whitespace(self):
        app = FastAPI()
        app.include_router(widget_visitor.router, prefix="/v1")
        app.state.database = SimpleNamespace()
        widget_id, session_id, chunk_id = uuid4(), uuid4(), uuid4()
        row = dict(
            id=chunk_id,
            document_id=uuid4(),
            filename="fixture.pdf",
            page_number=1,
            chunk_index=0,
            content='  A quoted "passage" with trailing whitespace.\n  ',
        )
        with (
            patch(
                "app.api.v1.widget_visitor.visitor", AsyncMock(return_value=({}, {}))
            ),
            patch(
                "app.api.v1.widget_visitor.visitor_passage", AsyncMock(return_value=row)
            ),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://127.0.0.1"
            ) as client:
                response = await client.get(
                    f"/v1/widget/{widget_id}/sessions/{session_id}/passages/{chunk_id}",
                    headers={"X-Widget-Token": "a" * 64},
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, JSONResponse(jsonable_encoder(row)).body)

    async def test_route_error_messages_are_configurable_and_keep_legacy_widget_copy(
        self,
    ):
        class CustomRoute(ConfigurationRoute):
            storage_error_detail = "Custom configuration storage is unavailable."

        for route_class, expected in (
            (
                WidgetConfigurationRoute,
                "Assistant configuration storage is temporarily unavailable.",
            ),
            (CustomRoute, "Custom configuration storage is unavailable."),
        ):
            app = FastAPI()
            router = APIRouter(route_class=route_class)

            @router.get("/failure")
            async def fail():
                raise SQLAlchemyError("PRIVATE_DATABASE_DETAILS")

            app.include_router(router)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://127.0.0.1"
            ) as client:
                response = await client.get("/failure")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {"detail": expected})
            self.assertNotIn("PRIVATE_DATABASE_DETAILS", response.text)
