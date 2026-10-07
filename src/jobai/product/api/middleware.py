"""Pure-ASGI middleware for the product API (no BaseHTTPMiddleware: it buffers
and breaks contextvars/streaming).

  * RequestContextMiddleware — X-Request-ID in/out, log context, one access-log
    line per request (method, route template, status, duration; never the query
    string or body).
  * SecurityHeadersMiddleware — nosniff, Referrer-Policy, frame-ancestors 'none',
    HSTS outside dev.
  * BodySizeLimitMiddleware — 413 for any body over MAX_BODY_BYTES (declared or streamed).
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid

from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from jobai.product import observability

access_log = logging.getLogger("product.access")

MAX_BODY_BYTES = 3 * 1024 * 1024  # resume upload cap is 2MB + multipart overhead
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _route_path(scope: Scope) -> str:
    route = scope.get("route")
    return getattr(route, "path", None) or "<unmatched>"


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = observability.new_context(request_id=request_id)
        start = time.perf_counter()
        status = {"code": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                headers = list(message.get("headers") or [])
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        started = {"v": False}

        async def tracking(message: Message) -> None:
            if message["type"] == "http.response.start":
                started["v"] = True
            await send_wrapper(message)

        try:
            await self.app(scope, receive, tracking)
        except Exception:
            # Unhandled: log once (the Sentry logging integration turns this into an
            # event) and answer in the API's error shape, request id included.
            access_log.exception("unhandled error", extra={"method": scope.get("method"), "path": _route_path(scope)})
            if started["v"]:
                raise
            status["code"] = 500
            body = json.dumps({"error": {"code": "internal_error", "message": "internal error",
                                         "request_id": request_id}}).encode()
            await send({"type": "http.response.start", "status": 500, "headers": [
                (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                (b"x-request-id", request_id.encode())]})
            await send({"type": "http.response.body", "body": body})
        finally:
            state = scope.get("state") or {}
            if state.get("user_id") is not None:
                observability.bind(user_id=state["user_id"])
            path = _route_path(scope)
            if path not in ("/health",):  # keep platform health probes out of the logs
                access_log.info("request", extra={
                    "method": scope.get("method"), "path": path, "status": status["code"],
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                })
            observability.reset_context(token)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, hsts: bool):
        self.app = app
        self.headers = [
            (b"x-content-type-options", b"nosniff"),
            (b"referrer-policy", b"no-referrer"),
            (b"x-frame-options", b"DENY"),
            (b"content-security-policy", b"frame-ancestors 'none'"),
            (b"cross-origin-resource-policy", b"same-site"),
        ]
        if hsts:
            self.headers.append((b"strict-transport-security", b"max-age=63072000; includeSubDomains"))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                existing = {k.lower() for k, _ in message.get("headers") or []}
                message["headers"] = list(message.get("headers") or []) + [h for h in self.headers if h[0] not in existing]
            await send(message)

        await self.app(scope, receive, send_wrapper)


class _TooLarge(HTTPException):
    """An HTTPException so FastAPI's body parsing re-raises it (instead of turning
    it into a 400) and the app's error handler renders the usual 413 shape."""

    def __init__(self, limit: int) -> None:
        super().__init__(413, f"request body exceeds {limit} bytes")


async def _send_413(send: Send, limit: int) -> None:
    body = json.dumps({"error": {"code": "too_large", "message": f"request body exceeds {limit} bytes"}}).encode()
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                            (b"connection", b"close")]})
    await send({"type": "http.response.body", "body": body})


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None:
            try:
                if int(declared) > self.max_bytes:
                    await _send_413(send, self.max_bytes)
                    return
            except ValueError:
                pass
        received = 0
        started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _TooLarge(self.max_bytes)
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _TooLarge:
            if not started:
                await _send_413(send, self.max_bytes)
