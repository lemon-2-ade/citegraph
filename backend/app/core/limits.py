"""Request limits: body size and per-client rate limits (pure ASGI, no buffering).

Rate limiting is a sliding window held in process memory. It protects one instance from a
single abusive client and bounds LLM spend per client; it is not shared between replicas
(put a gateway or a Redis-backed limiter in front for multi-instance deployments).
"""

from __future__ import annotations

import json
import math
import re
import time
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger

log = get_logger(__name__)

# Endpoints that call a paid LLM (or are otherwise expensive) get the stricter bucket.
_AI_ROUTES = (
    ("POST", re.compile(r"^/api/ask$")),
    ("POST", re.compile(r"^/api/query$")),
    ("POST", re.compile(r"^/api/papers/[^/]+/insight$")),
)
_EXEMPT = re.compile(r"^/api/health(/|$)")
MAX_TRACKED_CLIENTS = 10_000


def _error(status: int, code: str, message: str, headers: list[tuple[bytes, bytes]]) -> Any:
    body = json.dumps({"error": {"code": code, "message": message}}).encode()

    async def respond(send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    *headers,
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    return respond


class BodyLimitMiddleware:
    """Reject request bodies larger than ``max_bytes`` (413), whether or not they declare a size."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length")
        too_big = _error(413, "payload_too_large", "Request body is too large.", [])
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            await too_big(send)
            return

        seen = 0
        started = False

        async def counting_receive() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    raise _BodyTooLargeError
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _BodyTooLargeError:
            if not started:
                await too_big(send)


class _BodyTooLargeError(Exception):
    pass


class SlidingWindowLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def check(self, client: str, bucket: str, limit: int, window: float = 60.0) -> float:
        """Record a hit. Returns 0 if allowed, else seconds until a slot frees up."""
        now = self._clock()
        hits = self._hits[(client, bucket)]
        while hits and hits[0] <= now - window:
            hits.popleft()
        if len(hits) >= limit:
            return max(0.0, hits[0] + window - now)
        hits.append(now)
        if len(self._hits) > MAX_TRACKED_CLIENTS:
            self._evict(now, window)
        return 0.0

    def _evict(self, now: float, window: float) -> None:
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= now - window]:
            del self._hits[key]


class RateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        per_minute: int,
        ai_per_minute: int,
        trust_forwarded_for: bool = False,
        limiter: SlidingWindowLimiter | None = None,
    ) -> None:
        self.app = app
        self.per_minute = per_minute
        self.ai_per_minute = ai_per_minute
        self.trust_forwarded_for = trust_forwarded_for
        self.limiter = limiter or SlidingWindowLimiter()

    def _client(self, scope: Scope) -> str:
        if self.trust_forwarded_for:
            forwarded = dict(scope["headers"]).get(b"x-forwarded-for", b"").decode("latin-1")
            first = forwarded.split(",")[0].strip()
            if first:
                return str(first[:64])
        client = scope.get("client")
        return str(client[0]) if client else "unknown"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or _EXEMPT.match(scope["path"]):
            await self.app(scope, receive, send)
            return
        method, path = scope["method"], scope["path"]
        is_ai = any(method == m and rx.match(path) for m, rx in _AI_ROUTES)
        bucket, limit = ("ai", self.ai_per_minute) if is_ai else ("default", self.per_minute)
        client = self._client(scope)
        wait = self.limiter.check(client, bucket, limit)
        if wait > 0:
            retry = str(math.ceil(wait)).encode()
            log.warning("ratelimit.blocked", bucket=bucket, path=path)
            respond = _error(
                429, "rate_limited", "Too many requests. Please slow down.",
                [(b"retry-after", retry)],
            )  # fmt: skip
            await respond(send)
            return
        await self.app(scope, receive, send)
