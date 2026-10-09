"""Small latency probe for a running ResearchGraph API.

Usage:  python scripts/loadtest.py --base http://localhost:8000 --requests 50 --concurrency 8

Hits the read endpoints a user touches most and prints p50/p95/max latency and error counts.
LLM-backed endpoints are excluded by default because they cost money (use --with-ai).
Needs only httpx. Run it against your own data; results depend on graph size and hardware.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx

READ_ENDPOINTS = [
    ("summary", "GET", "/api/analytics/summary", None),
    ("papers list", "GET", "/api/papers?page_size=20", None),
    ("keyword search", "GET", "/api/search/papers?q=graph&mode=keyword", None),
    ("hybrid search", "GET", "/api/search/papers?q=making%20transformers%20efficient", None),
    ("graph overview", "GET", "/api/graph/overview?limit=150", None),
    ("topic trends", "GET", "/api/trends/topics", None),
    (
        "influential",
        "GET",
        "/api/analytics/influential?entity=paper&metric=pagerank&limit=10",
        None,
    ),
]
AI_ENDPOINTS = [
    ("ask", "POST", "/api/ask", {"question": "How does retrieval improve language models?"}),
    ("nl query", "POST", "/api/query", {"question": "Who are the most influential authors?"}),
]


async def probe(client: httpx.AsyncClient, method: str, path: str, body: object, n: int, c: int):
    gate = asyncio.Semaphore(c)
    latencies: list[float] = []
    errors: dict[int, int] = {}

    async def one() -> None:
        async with gate:
            start = time.perf_counter()
            try:
                res = await client.request(method, path, json=body)
                status = res.status_code
            except httpx.HTTPError:
                status = 0
            elapsed = (time.perf_counter() - start) * 1000
            if status == 200:
                latencies.append(elapsed)
            else:
                errors[status] = errors.get(status, 0) + 1

    await asyncio.gather(*(one() for _ in range(n)))
    return latencies, errors


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--requests", type=int, default=40)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--token", default=None, help="X-Admin-Token for gated endpoints")
    parser.add_argument(
        "--with-ai", action="store_true", help="also probe LLM endpoints (costs money)"
    )
    args = parser.parse_args()
    headers = {"X-Admin-Token": args.token} if args.token else {}
    targets = READ_ENDPOINTS + (AI_ENDPOINTS if args.with_ai else [])
    print(f"{'endpoint':<16}{'ok':>5}{'p50 ms':>10}{'p95 ms':>10}{'max ms':>10}  errors")
    async with httpx.AsyncClient(base_url=args.base, headers=headers, timeout=120) as client:
        for name, method, path, body in targets:
            n = min(args.requests, 5) if body else args.requests  # be gentle with paid calls
            lat, errs = await probe(client, method, path, body, n, args.concurrency)
            if lat:
                q = statistics.quantiles(lat, n=20) if len(lat) >= 2 else [lat[0]] * 19
                print(
                    f"{name:<16}{len(lat):>5}{statistics.median(lat):>10.0f}"
                    f"{q[18]:>10.0f}{max(lat):>10.0f}  {errs or ''}"
                )
            else:
                print(f"{name:<16}{0:>5}{'-':>10}{'-':>10}{'-':>10}  {errs}")
    print(
        "\n429 means the rate limiter engaged; lower --concurrency or raise RATE_LIMIT_PER_MINUTE."
    )


if __name__ == "__main__":
    asyncio.run(main())
