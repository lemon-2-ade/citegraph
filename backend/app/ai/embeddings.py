"""Embedding providers: OpenAI, a local CPU model, and a deterministic offline stand-in.

Selection (``EMBEDDING_PROVIDER=auto``, the default): OpenAI when ``OPENAI_API_KEY`` is set,
otherwise a small open model run locally with fastembed (ONNX, no GPU needed). Vectors from
different models are not comparable, so the model name is stored alongside the vectors and
searching refuses to mix them (see ``EmbeddingRepository``).
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
from collections.abc import Sequence
from typing import Any, Protocol

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.core.config import Settings
from app.core.errors import DependencyUnavailableError
from app.core.logging import get_logger

log = get_logger(__name__)

MAX_TEXT_CHARS = 6000  # ~1,500 tokens; titles and abstracts are far shorter
_OPENAI_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimensions: int

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def paper_text(title: str | None, abstract: str | None, description: str | None) -> str:
    """The text that represents a paper: its title plus the abstract (or a description)."""
    body = (abstract or description or "").strip()
    text = f"{(title or '').strip()}\n\n{body}".strip()
    return text[:MAX_TEXT_CHARS]


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# --------------------------------------------------------------------------- hashing
_TOKEN = re.compile(r"[a-z0-9]+")


class HashingEmbeddings:
    """Hashed bag-of-words vectors: deterministic, offline, and lexically meaningful.

    Not a semantic model (synonyms are unrelated); it exists so the full vector pipeline
    can be tested and demoed without network access or model downloads.
    """

    name = "hashing"
    model = "hashing-bow-256"
    dimensions = 256

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _TOKEN.findall(text.lower()):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            slot = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[slot] += sign
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


# --------------------------------------------------------------------------- OpenAI
def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {408, 429, 500, 502, 503, 504}
    return isinstance(exc, httpx.TransportError)


class OpenAIEmbeddings:
    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        dimensions: int | None = None,
        base_url: str = "https://api.openai.com/v1",
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
        max_attempts: int = 5,
        retry_initial_wait: float = 1.0,
    ) -> None:
        native = _OPENAI_DIMENSIONS.get(model)
        if dimensions is None and native is None:
            raise ValueError(f"Unknown output size for {model!r}; set OPENAI_EMBEDDING_DIMENSIONS.")
        self.model = model
        self.dimensions = dimensions or native or 0
        self._requested = dimensions
        self._url = f"{base_url.rstrip('/')}/embeddings"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._max_attempts = max_attempts
        self._retry_wait = retry_initial_wait

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        payload: dict[str, Any] = {"model": self.model, "input": list(texts)}
        if self._requested is not None:
            payload["dimensions"] = self._requested
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception(_retryable),
                stop=stop_after_attempt(self._max_attempts),
                wait=wait_exponential_jitter(initial=self._retry_wait, max=20),
                reraise=True,
            ):
                with attempt:
                    response = await self._client.post(
                        self._url, json=payload, headers=self._headers
                    )
                    response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Never include the response body or headers: they can echo credentials.
            raise DependencyUnavailableError(
                f"OpenAI embeddings request failed with HTTP {exc.response.status_code}"
            ) from None
        except httpx.TransportError as exc:
            raise DependencyUnavailableError(
                f"OpenAI embeddings request failed: {type(exc).__name__}"
            ) from None
        rows = sorted(response.json()["data"], key=lambda r: r["index"])
        return [list(map(float, r["embedding"])) for r in rows]


# --------------------------------------------------------------------------- local
class LocalEmbeddings:
    """CPU embeddings through fastembed (ONNX). The model downloads on first use."""

    name = "local"

    def __init__(self, model: str) -> None:
        try:
            from fastembed import TextEmbedding  # optional dependency, imported lazily
        except ImportError as exc:
            raise DependencyUnavailableError(
                "Local embeddings need the 'local' extra (uv sync --extra local), "
                "or set OPENAI_API_KEY to use OpenAI."
            ) from exc
        self.model = model
        self._model = TextEmbedding(model)
        self.dimensions = len(next(iter(self._model.embed(["dimension probe"]))))

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        return [[float(x) for x in v] for v in self._model.embed(texts)]

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        # Inference is CPU-bound and blocking: keep it off the event loop.
        return await asyncio.to_thread(self._embed_sync, list(texts))


def build_provider(settings: Settings) -> EmbeddingProvider:
    choice = settings.embedding_provider
    key = settings.openai_api_key
    if choice == "hashing":
        return HashingEmbeddings()
    if choice == "openai" and key is None:
        raise DependencyUnavailableError(
            "EMBEDDING_PROVIDER=openai but OPENAI_API_KEY is not set "
            "(use EMBEDDING_PROVIDER=auto to fall back to a local model)."
        )
    if choice in {"openai", "auto"} and key is not None:
        return OpenAIEmbeddings(
            key.get_secret_value(),
            settings.openai_embedding_model,
            dimensions=settings.openai_embedding_dimensions,
            base_url=settings.openai_base_url,
            timeout=settings.http_timeout_seconds,
        )
    return LocalEmbeddings(settings.local_embedding_model)


class EmbedderCache:
    """Builds the configured provider on first use and reuses it (loading a model is slow)."""

    def __init__(self, settings: Settings, provider: EmbeddingProvider | None = None) -> None:
        self._settings = settings
        self._provider = provider
        self._lock = asyncio.Lock()

    async def get(self) -> EmbeddingProvider:
        if self._provider is None:
            async with self._lock:
                if self._provider is None:
                    self._provider = await asyncio.to_thread(build_provider, self._settings)
        return self._provider
