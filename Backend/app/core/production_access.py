"""Password-protected shared workspace behind an HTTPS reverse proxy.

Every authenticated operator shares the same documents and administrator rights.
This is intentionally not a tenant/account system or a public visitor gateway.
"""

import base64
import binascii
from collections import deque
from hashlib import sha256
import re
import secrets
from time import monotonic
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from starlette.responses import JSONResponse

from app.core.config import Settings
from app.schemas.widgets import website_origin


def validate_production(settings: Settings) -> str:
    """Fail before binding a port when required deployment configuration is missing."""
    try:
        origin = website_origin(settings.app_public_origin or settings.render_external_url)
        if not origin.startswith("https://"):
            raise ValueError()
    except ValueError:
        raise RuntimeError("Set APP_PUBLIC_ORIGIN (or RENDER_EXTERNAL_URL) to the exact HTTPS workspace origin.") from None
    username = settings.workspace_username
    password = settings.workspace_password.get_secret_value()
    if (not username or ":" in username or len(username) > 128
            or any(ord(c) < 33 or ord(c) > 126 for c in username)
            or len(password) < 32 or len(password) > 256
            or any(ord(c) < 33 or ord(c) > 126 for c in password)):
        raise RuntimeError("Set WORKSPACE_USERNAME and a random WORKSPACE_PASSWORD of 32 to 256 printable ASCII characters.")
    try:
        Fernet(settings.assistant_encryption_key.get_secret_value().encode("ascii"))
    except (ValueError, UnicodeError):
        raise RuntimeError("Set a stable ASSISTANT_ENCRYPTION_KEY using Fernet.generate_key().") from None
    if not (settings.frontend_dist_dir / "index.html").is_file():
        raise RuntimeError("Frontend build missing. Build the repository-root Dockerfile or set FRONTEND_DIST_DIR.")
    if not settings.embedding_warmup_on_startup:
        raise RuntimeError("Production requires EMBEDDING_WARMUP_ON_STARTUP=true for readiness checks.")
    return origin


class ProductionAccessMiddleware:
    def __init__(self, app, *, origin: str, username: str, password: str):
        self.app = app
        self.origin = origin
        self.host = urlsplit(origin).netloc.encode("ascii")
        self.username_digest = sha256(username.encode("utf-8")).digest()
        self.password_digest = sha256(password.encode("utf-8")).digest()
        # Bounded, process-local failure window. Successful sign-ins remain usable.
        self.failures = deque(maxlen=60)

    def authenticated(self, header: bytes) -> bool:
        try:
            scheme, encoded = header.split(b" ", 1)
            if scheme.lower() != b"basic" or len(encoded) > 1024:
                return False
            username, password = base64.b64decode(encoded, validate=True).split(b":", 1)
        except (ValueError, binascii.Error):
            return False
        user_ok = secrets.compare_digest(sha256(username).digest(), self.username_digest)
        password_ok = secrets.compare_digest(sha256(password).digest(), self.password_digest)
        return user_ok and password_ok

    @staticmethod
    def public_widget_path(path: str) -> bool:
        return (path.startswith("/widget-assets/") or path.startswith("/v1/widget/")
            or re.fullmatch(r"/widget/[0-9a-fA-F-]{36}", path) is not None)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        if scope["type"] != "http":
            return await send({"type": "websocket.close", "code": 1008})

        async def secure_send(message):
            if message["type"] == "http.response.start":
                message = dict(message)
                headers = list(message.get("headers", []))
                names = {name.lower() for name, _ in headers}
                additions = {
                    b"cache-control": b"no-store",
                    b"strict-transport-security": b"max-age=31536000",
                    b"x-content-type-options": b"nosniff",
                    b"referrer-policy": b"no-referrer",
                    b"content-security-policy": (
                        b"default-src 'self'; script-src 'self'; "
                        b"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                        b"font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; "
                        b"connect-src 'self'; frame-src 'self'; frame-ancestors 'none'; "
                        b"object-src 'none'; base-uri 'none'; form-action 'self'"
                    ),
                }
                if self.public_widget_path(scope.get("path", "")):
                    additions[b"access-control-allow-origin"] = b"*"
                headers.extend((name, value) for name, value in additions.items() if name not in names)
                message["headers"] = headers
            await send(message)

        # Ignore all externally supplied state; ASGI state is server-controlled.
        scope.setdefault("state", {})["workspace_authenticated"] = False
        headers = dict(scope.get("headers", []))
        if headers.get(b"host", b"").lower() != self.host:
            return await JSONResponse({"detail": "Workspace host unavailable."}, 400)(scope, receive, secure_send)
        public_widget = self.public_widget_path(scope.get("path", ""))
        origin = headers.get(b"origin")
        if not public_widget and origin is not None and origin != self.origin.encode("ascii"):
            return await JSONResponse({"detail": "Cross-origin requests are disabled."}, 403)(scope, receive, secure_send)
        # Basic credentials are browser-managed and automatically included by fetch.
        # Reject browser cross-site requests even when a GET has no Origin header.
        landing = (scope.get("method") == "GET" and scope.get("path") == "/"
                   and headers.get(b"sec-fetch-mode") == b"navigate")
        if not public_widget and headers.get(b"sec-fetch-site") == b"cross-site" and not landing:
            return await JSONResponse({"detail": "Cross-site requests are disabled."}, 403)(scope, receive, secure_send)
        probe = scope.get("method") == "GET" and scope.get("path") in {"/v1/health", "/v1/ready"}
        if not probe:
            authorization = headers.get(b"authorization", b"")
            if not self.authenticated(authorization):
                now = monotonic()
                while self.failures and self.failures[0] <= now - 60:
                    self.failures.popleft()
                if len(self.failures) == self.failures.maxlen:
                    return await JSONResponse({"detail": "Too many sign-in attempts. Try again shortly."}, 429,
                                              headers={"Retry-After": "60"})(scope, receive, secure_send)
                if authorization:
                    self.failures.append(now)
                return await JSONResponse({"detail": "Sign in to the shared workspace."}, 401,
                                          headers={"WWW-Authenticate": 'Basic realm="Document Assistant", charset="UTF-8"'})(scope, receive, secure_send)
            scope["state"]["workspace_authenticated"] = True
        return await self.app(scope, receive, secure_send)
