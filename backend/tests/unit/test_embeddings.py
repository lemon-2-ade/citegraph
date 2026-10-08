import json
from typing import Any

import httpx
import pytest

from app.ai import embeddings
from app.ai.embeddings import (
    EmbedderCache,
    HashingEmbeddings,
    OpenAIEmbeddings,
    build_provider,
    paper_text,
    text_hash,
)
from app.core.config import Settings
from app.core.errors import DependencyUnavailableError


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_paper_text_prefers_abstract_and_is_bounded() -> None:
    assert paper_text("T", "Abstract", "Desc") == "T\n\nAbstract"
    assert paper_text("T", None, "Desc") == "T\n\nDesc"
    assert paper_text(None, None, None) == ""
    assert len(paper_text("T", "x" * 100_000, None)) == embeddings.MAX_TEXT_CHARS
    assert text_hash("a") == text_hash("a") != text_hash("b")


async def test_hashing_embeddings_are_deterministic_unit_vectors() -> None:
    provider = HashingEmbeddings()
    a, b, c = await provider.embed(
        ["graph neural networks", "graph neural networks", "protein folding"]
    )
    assert a == b
    assert len(a) == provider.dimensions
    assert _cos(a, a) == pytest.approx(1.0)
    assert _cos(a, c) < 0.5


async def test_hashing_embeddings_rank_lexical_overlap_higher() -> None:
    provider = HashingEmbeddings()
    query, near, far = await provider.embed(
        ["attention mechanism", "self attention mechanism for translation", "kidney disease"]
    )
    assert _cos(query, near) > _cos(query, far)


def _openai(handler: Any, **kwargs: Any) -> OpenAIEmbeddings:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenAIEmbeddings(
        "sk-test", "text-embedding-3-small", client=client, retry_initial_wait=0.0, **kwargs
    )


async def test_openai_orders_results_by_index_and_sends_model() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        data = [
            {"index": 1, "embedding": [0.0, 1.0]},
            {"index": 0, "embedding": [1.0, 0.0]},
        ]
        return httpx.Response(200, json={"data": data})

    provider = _openai(handler, dimensions=2)
    vectors = await provider.embed(["a", "b"])
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert seen["body"] == {"model": "text-embedding-3-small", "input": ["a", "b"], "dimensions": 2}
    assert seen["auth"] == "Bearer sk-test"
    assert provider.dimensions == 2


async def test_openai_retries_rate_limits_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": {"message": "slow down"}})
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})

    assert await _openai(handler, dimensions=1).embed(["a"]) == [[1.0]]
    assert calls["n"] == 2


async def test_openai_failure_does_not_leak_response_body() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Incorrect API key sk-test"}})

    with pytest.raises(DependencyUnavailableError) as info:
        await _openai(handler).embed(["a"])
    assert "401" in info.value.message
    assert "sk-test" not in info.value.message


def test_openai_requires_known_or_explicit_dimensions() -> None:
    with pytest.raises(ValueError, match="OPENAI_EMBEDDING_DIMENSIONS"):
        OpenAIEmbeddings("k", "some-new-model")
    assert OpenAIEmbeddings("k", "some-new-model", dimensions=64).dimensions == 64


def test_provider_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    class StubLocal:
        name = "local"
        dimensions = 384

        def __init__(self, model: str) -> None:
            self.model = model

    monkeypatch.setattr(embeddings, "LocalEmbeddings", StubLocal)
    base: dict[str, Any] = {"log_json": False}

    assert isinstance(
        build_provider(Settings(embedding_provider="hashing", **base)), HashingEmbeddings
    )
    with_key = build_provider(Settings(openai_api_key="sk-x", **base))  # type: ignore[arg-type]
    assert with_key.name == "openai"
    assert with_key.model == "text-embedding-3-small"
    # No key: auto falls back to the local model, with the *local* model name.
    fallback = build_provider(Settings(**base))
    assert fallback.name == "local"
    assert fallback.model == "BAAI/bge-small-en-v1.5"
    # An explicit provider is honoured, not silently replaced.
    with pytest.raises(DependencyUnavailableError, match="OPENAI_API_KEY"):
        build_provider(Settings(embedding_provider="openai", **base))


async def test_embedder_cache_builds_once() -> None:
    cache = EmbedderCache(Settings(embedding_provider="hashing", log_json=False))
    first = await cache.get()
    assert await cache.get() is first
