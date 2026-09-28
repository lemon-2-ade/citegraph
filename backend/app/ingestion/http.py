"""HTTP plumbing for external sources: rate limiting and retries."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.core.logging import get_logger

log = get_logger(__name__)

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class RateLimiter:
    """Minimum-interval limiter shared by all requests of one client.

    Keeps request starts at least ``1 / rate`` seconds apart, which is what most
    scholarly APIs specify ("max N requests per second").
    """

    def __init__(self, requests_per_second: float) -> None:
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        self._interval = 1.0 / requests_per_second
        self._lock = asyncio.Lock()
        self._next_slot = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._next_slot - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()
            self._next_slot = now + self._interval


class RetryableHTTPError(Exception):
    def __init__(self, status_code: int, retry_after: float | None) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code
        self.retry_after = retry_after


class SourceHTTPError(Exception):
    """Non-retryable HTTP failure (4xx other than 408/425/429)."""

    def __init__(self, status_code: int, url: str) -> None:
        super().__init__(f"HTTP {status_code} for {url}")
        self.status_code = status_code


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
        except (TypeError, ValueError):
            return None


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, RetryableHTTPError | httpx.TransportError)


class HttpFetcher:
    """GET-with-JSON helper with rate limiting, retries and structured logging."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        limiter: RateLimiter,
        *,
        max_attempts: int = 5,
        max_backoff: float = 60.0,
    ) -> None:
        self._client = client
        self._limiter = limiter
        self._max_attempts = max_attempts
        self._max_backoff = max_backoff
        self.requests_made = 0

    def _wait(self, state: RetryCallState) -> float:
        exc = state.outcome.exception() if state.outcome else None
        if isinstance(exc, RetryableHTTPError) and exc.retry_after is not None:
            return min(exc.retry_after, self._max_backoff)
        return wait_exponential_jitter(initial=1, max=self._max_backoff)(state)

    async def get_json(self, url: str, params: Mapping[str, Any] | None = None) -> Any:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=self._wait,
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        ):
            with attempt:
                await self._limiter.acquire()
                self.requests_made += 1
                start = time.perf_counter()
                response = await self._client.get(url, params=params)
                latency_ms = round((time.perf_counter() - start) * 1000, 1)
                log.debug(
                    "http.get",
                    url=url,
                    status=response.status_code,
                    latency_ms=latency_ms,
                    attempt=attempt.retry_state.attempt_number,
                )
                if response.status_code in RETRYABLE_STATUS:
                    log.warning("http.retryable", url=url, status=response.status_code)
                    raise RetryableHTTPError(
                        response.status_code,
                        _parse_retry_after(response.headers.get("Retry-After")),
                    )
                if response.status_code == 404:
                    return None
                if response.is_error:
                    raise SourceHTTPError(response.status_code, url)
                return response.json()
        raise AssertionError("unreachable")  # pragma: no cover
