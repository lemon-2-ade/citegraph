"""HTTP middleware: request IDs, access logging with latency, security headers."""

from __future__ import annotations

import re
import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.logging import get_logger

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

log = get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request ID, binds it to the log context and records latency."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        # Accept a caller-supplied ID only if it is well-formed (avoids log injection).
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("request.unhandled_error", method=request.method, path=request.url.path)
            raise
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = request_id
        log.info(
            "request.completed",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            latency_ms=latency_ms,
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Defensive headers. The JSON API never needs scripts, frames or sensors, so its CSP is
    empty; the interactive docs (which load assets) are exempt from the CSP only."""

    def __init__(self, app: ASGIApp, *, hsts: bool = False, docs_prefix: str = "/api/docs") -> None:
        super().__init__(app)
        self._hsts = hsts
        self._docs_prefix = docs_prefix

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if not request.url.path.startswith(self._docs_prefix):
            headers.setdefault(
                "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
            )
            headers.setdefault("Cache-Control", "no-store")
        if self._hsts:
            headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response
