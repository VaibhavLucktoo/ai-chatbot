"""Early input limits, local access, and request-scoped model resources."""

from uuid import uuid4
import asyncio
import logging
from urllib.parse import urlsplit
from time import perf_counter

from fastapi import HTTPException
from starlette.responses import JSONResponse

from app.core.local_access import is_workspace_scope
from app.core.framing import LOCAL_CSP, framing_headers, widget_route
from app.services.llm import llm_request_resources
from app.services.metrics import current_request

logger = logging.getLogger(__name__)


class LocalWorkspaceMiddleware:
    def __init__(self, app, *, state, max_active_requests: int,
                 widget_public_enabled=False, widget_public_origin="http://127.0.0.1:8000",
                 workspace_origin=""):
        self.app, self.state = app, state
        self.max_active_requests = max_active_requests
        self.active_requests = 0
        self.active_uploads = 0
        self.widget_public_enabled = widget_public_enabled
        self.widget_public_origin = widget_public_origin
        self.workspace_origin = workspace_origin

    widget_route = staticmethod(widget_route)

    async def __call__(self, scope, receive, send):
        original_send = send

        async def framed_send(message):
            # Production's outer middleware owns private workspace headers.
            if message["type"] == "http.response.start" and (
                not self.workspace_origin or self.widget_route(scope)
            ):
                message = dict(message)
                message["headers"] = framing_headers(
                    message.get("headers", []), widget=self.widget_route(scope),
                    asset=scope.get("path", "").startswith("/widget-assets/"),
                    workspace_policy=LOCAL_CSP,
                )
            await original_send(message)

        send = framed_send
        collector = getattr(self.state, "metrics", None)
        is_widget_chat = scope.get("path", "").startswith("/v1/widget/") and scope.get("path", "").endswith("/chat")
        if collector is not None and scope["type"] == "http" and scope.get("method") == "POST" and (scope.get("path") in {"/v1/chat", "/v1/admin/chat"} or is_widget_chat):
            with collector.request("/v1/widget/chat" if is_widget_chat else scope["path"]) as measurement:
                async def measured_send(message):
                    if message["type"] == "http.response.start":
                        measurement.http_status = message["status"]
                    await send(message)
                return await self._handle(scope, receive, measured_send)
        return await self._handle(scope, receive, send)

    async def _handle(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        metric = current_request()
        request_id = metric.id.hex if metric is not None else uuid4().hex
        started, response_status = perf_counter(), 500
        widget_route = self.widget_route(scope)
        public_widget = self.widget_public_enabled and widget_route
        if public_widget:
            host = dict(scope.get("headers", [])).get(b"host", b"").decode("ascii", errors="replace").lower()
            if host != urlsplit(self.widget_public_origin).netloc.lower():
                return await JSONResponse({"detail": "Widget host unavailable."}, 403)(scope, receive, send)
        elif not (is_workspace_scope(scope) or (
            self.workspace_origin and scope.get("method") == "GET"
            and scope.get("path") in {"/v1/health", "/v1/ready"}
        )):
            return await JSONResponse({"detail": "Local access only.", "request_id": request_id}, 403)(scope, receive, send)
        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin")
        if not public_widget:
            if origin:
                expected = (self.workspace_origin.encode() if self.workspace_origin else
                            scope.get("scheme", "http").encode() + b"://" + headers.get(b"host", b""))
                if origin != expected:
                    return await JSONResponse({"detail": "Cross-origin requests are disabled."}, 403)(scope, receive, send)
        elif scope.get("path", "").startswith("/v1/widget/"):
            if scope.get("method") == "POST" and not origin:
                return await JSONResponse({"detail": "Widget origin is required."}, 403)(scope, receive, send)
            if origin and origin != self.widget_public_origin.encode("ascii"):
                return await JSONResponse({"detail": "Invalid widget API origin."}, 403)(scope, receive, send)
        upload = scope.get("path", "").endswith(("/documents/upload", "/documents/jobs"))
        costly = scope.get("method") == "POST"
        if costly and (self.active_requests >= self.max_active_requests or (upload and self.active_uploads)):
            return await JSONResponse({"detail": "The local workspace is busy. Try again shortly.", "request_id": request_id},
                                      429, headers={"Retry-After": "2"})(scope, receive, send)
        limit = 10 * 1024 * 1024 + 256 * 1024 if upload else 32 * 1024
        try:
            length = int(headers.get(b"content-length", b"0"))
            if length < 0:
                raise ValueError
        except ValueError:
            return await JSONResponse({"detail": "Invalid Content-Length."}, 400)(scope, receive, send)
        if length > limit:
            return await JSONResponse({"detail": "Request body exceeds the size limit."}, 413)(scope, receive, send)
        received, rejection = 0, None
        receive_deadline = perf_counter() + 60

        async def bounded_receive():
            nonlocal received, rejection
            try:
                async with asyncio.timeout(min(15, max(0, receive_deadline - perf_counter()))):
                    message = await receive()
            except TimeoutError:
                rejection = (408, "Request body reception timed out.")
                raise HTTPException(*rejection) from None
            received += len(message.get("body", b""))
            if received > limit:
                rejection = (413, "Request body exceeds the size limit.")
                raise HTTPException(413, "Request body exceeds the size limit.")
            return message

        async def decorated_send(message):
            nonlocal response_status
            if rejection:
                if message["type"] == "http.response.start":
                    response_status = rejection[0]
                    await JSONResponse({"detail": rejection[1]}, rejection[0])(scope, receive, send)
                return
            if message["type"] == "http.response.start":
                response_status = message["status"]
                message = dict(message)
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-request-id", request_id.encode()), (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer"),
                ]
                if scope.get("path", "").startswith("/widget-assets/"):
                    if not any(name.lower() == b"access-control-allow-origin" for name, _ in message["headers"]):
                        message["headers"].append((b"access-control-allow-origin", b"*"))
            await send(message)

        if costly:
            self.active_requests += 1
            self.active_uploads += int(upload)
        try:
            with llm_request_resources(getattr(self.state, "llm_client", None), getattr(self.state, "llm_slots", None)):
                await self.app(scope, bounded_receive, decorated_send)
        finally:
            logger.info("request id=%s method=%s status=%s duration_ms=%.2f", request_id,
                        scope.get("method"), response_status, (perf_counter() - started) * 1000)
            if costly:
                self.active_requests -= 1
                self.active_uploads -= int(upload)
