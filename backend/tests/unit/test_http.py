import time

import httpx
import pytest

from app.ingestion.http import HttpFetcher, RateLimiter, SourceHTTPError


def _fetcher(handler, *, attempts: int = 3) -> HttpFetcher:  # type: ignore[no-untyped-def]
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return HttpFetcher(client, RateLimiter(1000), max_attempts=attempts, max_backoff=0.01)


async def test_retries_on_429_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"ok": True})

    assert await _fetcher(handler).get_json("https://example.org/x") == {"ok": True}
    assert calls["n"] == 3


async def test_gives_up_after_max_attempts() -> None:
    fetcher = _fetcher(lambda r: httpx.Response(503), attempts=2)
    with pytest.raises(Exception, match="HTTP 503"):
        await fetcher.get_json("https://example.org/x")
    assert fetcher.requests_made == 2


async def test_client_errors_are_not_retried() -> None:
    fetcher = _fetcher(lambda r: httpx.Response(400))
    with pytest.raises(SourceHTTPError):
        await fetcher.get_json("https://example.org/x")
    assert fetcher.requests_made == 1


async def test_404_returns_none() -> None:
    assert await _fetcher(lambda r: httpx.Response(404)).get_json("https://example.org/x") is None


async def test_transport_errors_are_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json=[])

    assert await _fetcher(handler).get_json("https://example.org/x") == []


async def test_rate_limiter_spaces_requests() -> None:
    limiter = RateLimiter(20)  # 50 ms interval
    start = time.monotonic()
    for _ in range(4):
        await limiter.acquire()
    assert time.monotonic() - start >= 0.14
