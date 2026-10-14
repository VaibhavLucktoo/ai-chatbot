"""Early input limits, local access, and request-scoped model resources."""

from uuid import uuid4
import asyncio
import logging
from time import perf_counter

from fastapi import HTTPException
from starlette.responses import JSONResponse

from app.core.local_access import is_local_scope
from app.services.llm import llm_request_resources
from app.services.metrics import current_request

logger = logging.getLogger(__name__)


class LocalWorkspaceMiddleware:
    def __init__(self, app, *, state, max_active_requests: int):
        self.app, self.state = app, state
        self.max_active_requests = max_active_requests
        self.active_requests = 0
        self.active_uploads = 0

    async def __call__(self, scope, receive, send):
        collector = getattr(self.state, "metrics", None)
        if collector is not None and scope["type"] == "http" and scope.get("method") == "POST" and scope.get("path") in {"/v1/chat", "/v1/admin/chat"}:
            with collector.request(scope["path"]) as measurement:
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
        if not is_local_scope(scope):
            return await JSONResponse({"detail": "Local access only.", "request_id": request_id}, 403)(scope, receive, send)
        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin")
        if origin:
            expected = scope.get("scheme", "http").encode() + b"://" + headers.get(b"host", b"")
            if origin != expected:
                return await JSONResponse({"detail": "Cross-origin requests are disabled."}, 403)(scope, receive, send)
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
                if scope.get("path", "").startswith("/admin") or scope.get("path") == "/":
                    message["headers"].append((b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"))
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
