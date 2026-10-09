"""LLM provider abstraction (ADR-007).

One narrow interface, ``LLMProvider.complete``, returning text (optionally constrained to a
JSON object). OpenAI, Gemini and Ollama all expose an OpenAI-compatible chat-completions
endpoint, so a single HTTP client covers the three; only the base URL, key and model differ.
Callers never see provider SDKs, and tests use a scripted fake.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ValidationError
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.core.config import Settings
from app.core.errors import DependencyUnavailableError, ResearchGraphError
from app.core.logging import get_logger

log = get_logger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"


class LLMOutputError(ResearchGraphError):
    """The model answered, but not with output that matches the requested schema."""

    status_code = 502
    code = "llm_invalid_output"


@dataclass(frozen=True)
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMProvider(Protocol):
    name: str
    model: str

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        json_mode: bool = False,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> Completion: ...


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {408, 429, 500, 502, 503, 504}
    return isinstance(exc, httpx.TransportError)


class OpenAICompatibleChat:
    """Chat completions over HTTP for OpenAI and any OpenAI-compatible server."""

    def __init__(
        self,
        name: str,
        model: str,
        *,
        base_url: str,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 60.0,
        max_attempts: int = 4,
        retry_initial_wait: float = 1.0,
    ) -> None:
        self.name = name
        self.model = model
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._max_attempts = max_attempts
        self._retry_wait = retry_initial_wait

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        json_mode: bool = False,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> Completion:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception(_retryable),
                stop=stop_after_attempt(self._max_attempts),
                wait=wait_exponential_jitter(initial=self._retry_wait, max=30),
                reraise=True,
            ):
                with attempt:
                    response = await self._client.post(
                        self._url, json=payload, headers=self._headers
                    )
                    response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Never include the body or headers: they can echo credentials or the prompt.
            raise DependencyUnavailableError(
                f"{self.name} chat request failed with HTTP {exc.response.status_code}"
            ) from None
        except httpx.TransportError as exc:
            raise DependencyUnavailableError(
                f"{self.name} chat request failed: {type(exc).__name__}"
            ) from None
        body = response.json()
        try:
            text = body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise LLMOutputError(f"{self.name} returned an unexpected response shape") from None
        usage = body.get("usage") or {}
        return Completion(
            text=text,
            model=str(body.get("model") or self.model),
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
        )


def build_llm(settings: Settings) -> LLMProvider:
    provider = settings.llm_provider
    if provider == "openai":
        if settings.openai_api_key is None:
            raise DependencyUnavailableError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set.")
        return OpenAICompatibleChat(
            "openai",
            settings.llm_model,
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.llm_timeout_seconds,
        )
    if provider == "gemini":
        if settings.gemini_api_key is None:
            raise DependencyUnavailableError("LLM_PROVIDER=gemini but GEMINI_API_KEY is not set.")
        return OpenAICompatibleChat(
            "gemini",
            settings.llm_model,
            base_url=GEMINI_BASE_URL,
            api_key=settings.gemini_api_key.get_secret_value(),
            timeout=settings.llm_timeout_seconds,
        )
    return OpenAICompatibleChat(
        "ollama",
        settings.llm_model,
        base_url=f"{settings.ollama_base_url.rstrip('/')}/v1",
        timeout=settings.llm_timeout_seconds,
    )


class LLMCache:
    """Builds the configured provider on first use and reuses it."""

    def __init__(self, settings: Settings, provider: LLMProvider | None = None) -> None:
        self._settings = settings
        self._provider = provider
        self._lock = asyncio.Lock()

    async def get(self) -> LLMProvider:
        if self._provider is None:
            async with self._lock:
                if self._provider is None:
                    self._provider = build_llm(self._settings)
        return self._provider


def _extract_json(text: str) -> Any:
    """Parse a JSON object, tolerating a Markdown code fence around it."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        cleaned = cleaned.rsplit("```", 1)[0]
    return json.loads(cleaned)


async def complete_structured[T: BaseModel](
    llm: LLMProvider,
    messages: Sequence[Message],
    schema: type[T],
    *,
    max_tokens: int = 1024,
    repair_attempts: int = 1,
) -> tuple[T, Completion]:
    """Ask for JSON and validate it against ``schema``.

    On invalid output the model is shown its own answer and the validation error once (by
    default) before giving up with ``LLMOutputError``. The error never contains model text.
    """
    convo = list(messages)
    last_problem = "no attempt"
    for attempt in range(repair_attempts + 1):
        completion = await llm.complete(convo, json_mode=True, max_tokens=max_tokens)
        try:
            return schema.model_validate(_extract_json(completion.text)), completion
        except json.JSONDecodeError:
            last_problem = "the reply was not valid JSON"
        except ValidationError as exc:
            fields = sorted({".".join(map(str, e["loc"])) for e in exc.errors()})
            last_problem = "invalid or missing fields: " + ", ".join(fields)
        log.warning("llm.invalid_output", provider=llm.name, attempt=attempt, problem=last_problem)
        convo = [
            *messages,
            Message("assistant", completion.text),
            Message(
                "user",
                f"That reply was rejected: {last_problem}. Reply with only the "
                "corrected JSON object.",
            ),
        ]
    raise LLMOutputError(f"{llm.name} did not return valid structured output ({last_problem})")
