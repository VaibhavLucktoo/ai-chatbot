"""Hosted workspace access, startup configuration and frontend integration."""

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from cryptography.fernet import Fernet
import httpx
import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.core.production_access import validate_production
from app import main
from app.services.widgets import require_website


PASSWORD = "test-only-password-" + "x" * 32
ORIGIN = "https://chat.example.com"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def production_settings(tmp_path):
    (tmp_path / "index.html").write_text('<div id="root">Hosted workspace</div>', encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('workspace')", encoding="utf-8")
    return Settings(_env_file=None, app_env="production", app_public_origin=ORIGIN,
                    workspace_username="admin", workspace_password=PASSWORD,
                    assistant_encryption_key=Fernet.generate_key().decode(),
                    frontend_dist_dir=tmp_path, postgres_db="test", postgres_user="test",
                    postgres_password="test")


@pytest.fixture
def hosted_app(production_settings, monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: production_settings)
    app = main.create_app()
    app.state.database = SimpleNamespace(is_ready=AsyncMock(return_value=True))
    app.state.embedding_ready = True
    return app


def transport(app, address="198.51.100.1"):
    return httpx.ASGITransport(app, client=(address, 1234))


def assert_workspace_framing(response):
    assert response.headers.get_list("x-frame-options") == ["DENY"]
    policies = response.headers.get_list("content-security-policy")
    assert len(policies) == 1
    assert policies[0].count("frame-ancestors 'none'") == 1


@pytest.fixture(params=[ORIGIN, "https://widgets.example.com"])
def public_hosted_app(production_settings, monkeypatch, request):
    settings = production_settings.model_copy(update={
        "widget_public_enabled": True, "widget_public_origin": request.param,
    })
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    app = main.create_app()
    app.state.database = SimpleNamespace()
    return app, request.param


def test_production_requires_complete_secure_configuration(production_settings):
    assert validate_production(production_settings) == ORIGIN
    for updates in (
        {"app_public_origin": "", "render_external_url": ""},
        {"app_public_origin": "http://localhost"},
        {"app_public_origin": "https://chat.example.com/path"},
        {"workspace_password": "short"},
        {"workspace_password": "x" * 32 + "\n"},
        {"workspace_username": "admin:other"},
        {"assistant_encryption_key": ""},
        {"assistant_encryption_key": "invalid"},
        {"embedding_warmup_on_startup": False},
        {"frontend_dist_dir": production_settings.frontend_dist_dir / "missing"},
        {"widget_public_enabled": True, "widget_public_origin": "http://localhost:8000"},
    ):
        # Revalidate updates to keep SecretStr fields typed.
        settings = Settings(_env_file=None, **(production_settings.model_dump() | updates))
        with pytest.raises(RuntimeError):
            validate_production(settings)
    fallback = production_settings.model_copy(update={"app_public_origin": "", "render_external_url": ORIGIN})
    assert validate_production(fallback) == ORIGIN


@pytest.mark.anyio
async def test_every_workspace_surface_requires_authentication(hosted_app):
    async with httpx.AsyncClient(transport=transport(hosted_app), base_url=ORIGIN) as client:
        for method, path in (
            ("GET", "/"), ("GET", "/assets/app.js"), ("GET", "/admin"),
            ("GET", "/admin-assets/app.js"), ("GET", "/docs"), ("GET", "/openapi.json"),
            ("GET", "/v1/documents"), ("GET", "/v1/assistants"),
            ("GET", "/v1/admin/session"), ("POST", "/v1/chat"),
            ("POST", "/v1/documents/upload"), ("DELETE", "/v1/admin/assistants/example"),
            ("GET", "/widget-assets/loader.js"),
        ):
            response = await client.request(method, path)
            assert response.status_code == 401, path
            assert response.headers["www-authenticate"].startswith("Basic ")
            assert response.headers["cache-control"] == "no-store"
            assert "strict-transport-security" in response.headers
            assert_workspace_framing(response)
        for header in ("Basic !invalid!", "Bearer abc", "Basic " + base64.b64encode(b"missing-colon").decode()):
            assert (await client.get("/", headers={"Authorization": header})).status_code == 401
        assert (await client.get("/", auth=("admin", "incorrect"))).status_code == 401
        assert (await client.get("/", auth=("other", PASSWORD))).status_code == 401


@pytest.mark.anyio
async def test_authenticated_frontend_admin_session_and_protected_admin_route(hosted_app):
    async with httpx.AsyncClient(transport=transport(hosted_app), base_url=ORIGIN, auth=("admin", PASSWORD)) as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert "Hosted workspace" in response.text
        assert "fonts.googleapis.com" in response.headers["content-security-policy"]
        assert_workspace_framing(response)
        assert (await client.get("/assets/app.js")).status_code == 200
        assert (await client.get("/v1/unknown-route")).status_code == 404
        admin = await client.get("/admin")
        assert admin.status_code == 200
        assert_workspace_framing(admin)
        session = await client.get("/v1/admin/session")
        assert session.status_code == 200
        token = session.json()["token"]
        # This route has no database dependency, and still requires the admin token.
        assert (await client.get("/v1/admin/providers")).status_code == 403
        assert (await client.get("/v1/admin/providers", headers={"X-Admin-Token": token})).status_code == 200
        assert (await client.get("/docs")).status_code == 404
        assert (await client.get("/openapi.json")).status_code == 404


@pytest.mark.anyio
async def test_health_is_public_and_readiness_reflects_dependencies(hosted_app):
    async with httpx.AsyncClient(transport=transport(hosted_app), base_url=ORIGIN) as client:
        assert (await client.get("/v1/health")).status_code == 200
        assert (await client.get("/v1/ready")).status_code == 200
        hosted_app.state.embedding_ready = False
        assert (await client.get("/v1/ready")).status_code == 503
        hosted_app.state.embedding_ready = True
        hosted_app.state.database.is_ready.return_value = False
        assert (await client.get("/v1/ready")).status_code == 503
        assert (await client.post("/v1/health")).status_code == 401


@pytest.mark.anyio
async def test_host_origin_and_fetch_metadata_are_enforced_behind_tls_proxy(hosted_app):
    # The ASGI connection is HTTP because Render terminates TLS at its proxy.
    async with httpx.AsyncClient(transport=transport(hosted_app), base_url="http://chat.example.com",
                                auth=("admin", PASSWORD)) as client:
        assert (await client.get("/v1/admin/session", headers={"Origin": ORIGIN})).status_code == 200
        for header in ({"Origin": "https://evil.example"}, {"Origin": "null"},
                       {"Sec-Fetch-Site": "cross-site"}):
            assert (await client.get("/v1/admin/session", headers=header)).status_code == 403
        assert (await client.get("/", headers={"Host": "evil.example"})).status_code == 400
        assert (await client.get("/", headers={"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate"})).status_code == 200
    async with httpx.AsyncClient(transport=transport(hosted_app, "127.0.0.1"), base_url=ORIGIN) as client:
        # Loopback or forged proxy headers cannot bypass production authentication.
        assert (await client.get("/", headers={"X-Forwarded-For": "127.0.0.1", "X-Admin-Token": hosted_app.state.admin_token})).status_code == 401


@pytest.mark.anyio
async def test_failed_signins_are_bounded_without_locking_out_valid_credentials(hosted_app):
    async with httpx.AsyncClient(transport=transport(hosted_app), base_url=ORIGIN) as client:
        for _ in range(60):
            assert (await client.get("/", auth=("admin", "wrong"))).status_code == 401
        response = await client.get("/", auth=("admin", "wrong"))
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "60"
        assert (await client.get("/", auth=("admin", PASSWORD))).status_code == 200


@pytest.mark.anyio
async def test_public_widget_assets_and_dynamic_iframe_policy(public_hosted_app, monkeypatch):
    app, widget_origin = public_hosted_app
    widget_id = uuid4()
    allowed = "https://shop.example.com"
    widget = dict(title="Assistant", greeting="Hello", color="#2563eb", position="right",
                  revision=1, allowed_origins=[allowed, "https://www.shop.example.com"])

    async def page(database, identifier, parent):
        assert identifier == widget_id
        require_website(widget, parent)
        return widget

    monkeypatch.setattr("app.api.v1.widget_assets.widget_page", page)
    async with httpx.AsyncClient(transport=transport(app), base_url=widget_origin,
                                headers={"Sec-Fetch-Site": "cross-site"}) as client:
        for asset in ("loader.js", "chat.js", "style.css", "missing.js"):
            response = await client.get(f"/widget-assets/{asset}", headers={"Origin": allowed})
            assert response.status_code == (404 if asset == "missing.js" else 200)
            assert "www-authenticate" not in response.headers
            assert "x-frame-options" not in response.headers
            assert response.headers.get_list("content-security-policy") == ["frame-ancestors *"]
            assert response.headers.get_list("access-control-allow-origin") == ["*"]
        frame = await client.get(f"/widget/{widget_id}", params={"parent_origin": allowed})
        assert frame.status_code == 200
        assert "x-frame-options" not in frame.headers
        policies = frame.headers.get_list("content-security-policy")
        assert len(policies) == 1
        assert "frame-ancestors https://shop.example.com https://www.shop.example.com;" in policies[0]
        assert "frame-ancestors 'none'" not in policies[0]
        assert "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'" in policies[0]
        for parent in ("https://evil.example.com", "https://shop.example.com;script-src *"):
            response = await client.get(f"/widget/{widget_id}", params={"parent_origin": parent})
            assert response.status_code == 403
            assert "www-authenticate" not in response.headers
            assert "x-frame-options" not in response.headers
            assert len(response.headers.get_list("content-security-policy")) == 1


@pytest.mark.anyio
async def test_public_visitor_apis_use_widget_capabilities_without_workspace_auth(public_hosted_app, monkeypatch):
    app, widget_origin = public_hosted_app
    widget_id, session_id, chunk_id, document_id = uuid4(), uuid4(), uuid4(), uuid4()
    allowed, token = "https://shop.example.com", "b" * 64
    widget = {"allowed_origins": [allowed]}

    async def start(database, identifier, parent):
        require_website(widget, parent)
        return {"session_id": session_id, "token": token, "expires_at": "2099-01-01T00:00:00Z"}

    async def visitor(database, identifier, session, supplied_token):
        if supplied_token != token:
            raise HTTPException(403, "Invalid visitor capability.")
        return widget, {"id": session_id}

    monkeypatch.setattr("app.api.v1.widget_visitor.start_visitor", start)
    monkeypatch.setattr("app.api.v1.widget_visitor.visitor", visitor)
    monkeypatch.setattr("app.api.v1.widget_visitor.visitor_passage", AsyncMock(return_value={
        "id": chunk_id, "document_id": document_id, "filename": "guide.pdf",
        "page_number": 1, "chunk_index": 0, "content": "Passage",
    }))
    async with httpx.AsyncClient(transport=transport(app), base_url=widget_origin) as client:
        path = f"/v1/widget/{widget_id}/sessions"
        headers = {"Origin": widget_origin, "Sec-Fetch-Site": "cross-site"}
        response = await client.post(path, json={"parent_origin": allowed}, headers=headers)
        assert response.status_code == 201
        assert "www-authenticate" not in response.headers
        assert "x-frame-options" not in response.headers
        for origin in (None, allowed, "https://evil.example.com", "null"):
            response = await client.post(path, json={"parent_origin": allowed},
                                         headers={"Origin": origin} if origin else {})
            assert response.status_code == 403
        response = await client.post(path, json={"parent_origin": "https://evil.example.com"}, headers=headers)
        assert response.status_code == 403
        passage = f"{path}/{session_id}/passages/{chunk_id}"
        response = await client.get(passage, headers={"X-Widget-Token": token})
        assert response.status_code == 200
        assert response.json()["content"] == "Passage"
        assert (await client.get(passage)).status_code == 403
        assert (await client.get(passage, headers={"X-Widget-Token": token, "Origin": allowed})).status_code == 403


@pytest.mark.anyio
async def test_public_widget_access_never_grants_workspace_access(public_hosted_app):
    app, widget_origin = public_hosted_app
    async with httpx.AsyncClient(transport=transport(app), base_url=ORIGIN) as client:
        for path in ("/", "/admin", "/v1/admin/session", "/v1/documents", "/v1/assistants",
                     "/widget/not-a-uuid", "/widget-assets/../admin", "/v1/widget-admin"):
            response = await client.get(path)
            assert response.status_code == 401
            assert_workspace_framing(response)
        for method, path in (("POST", "/widget-assets/loader.js"), ("PUT", f"/v1/widget/{uuid4()}/sessions")):
            response = await client.request(method, path)
            assert response.status_code == 401
            assert_workspace_framing(response)
        for path in ("/", "/admin"):
            response = await client.get(path, auth=("admin", PASSWORD))
            assert response.status_code == 200
            assert_workspace_framing(response)
        response = await client.get("/admin", auth=("admin", PASSWORD), headers={"Sec-Fetch-Site": "cross-site"})
        assert response.status_code == 403
        assert_workspace_framing(response)
        response = await client.get("/widget-assets/loader.js", headers={"Host": "evil.example.com"})
        assert response.status_code == 400
        assert_workspace_framing(response)
        if widget_origin != ORIGIN:
            response = await client.get("/widget-assets/loader.js")
            assert response.status_code == 403
            assert_workspace_framing(response)
    if widget_origin != ORIGIN:
        async with httpx.AsyncClient(transport=transport(app), base_url=widget_origin,
                                    auth=("admin", PASSWORD)) as client:
            response = await client.get("/admin")
            assert response.status_code == 400
            assert_workspace_framing(response)
