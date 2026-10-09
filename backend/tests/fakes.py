"""Test doubles."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class ScriptedGraph:
    """GraphClient stand-in returning canned rows keyed by query label.

    Records every call so tests can assert on parameters. Queries without a scripted
    label return ``default`` (empty list unless configured).
    """

    def __init__(self, responses: Mapping[str, list[dict[str, Any]]] | None = None) -> None:
        self.responses = dict(responses or {})
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.query_types: list[str] = []

    async def read(
        self, query: str, params: Mapping[str, Any] | None = None, *, label: str = ""
    ) -> list[dict[str, Any]]:
        self.calls.append((label, query, dict(params or {})))
        if label in self.responses:
            return self.responses[label]
        if "count(" in query and "AS total" in query:
            return [{"total": 0}]
        return []

    write = read

    async def run_readonly_unchecked(
        self, query: str, params: Mapping[str, Any] | None = None, *, label: str = "",
        tx_timeout: float | None = None,
    ) -> list[dict[str, Any]]:  # fmt: skip
        return await self.read(query, params, label=label)  # type: ignore[arg-type]

    async def query_type(self, query: str) -> str:
        self.calls.append(("query_type", query, {}))
        return self.query_types.pop(0) if self.query_types else "r"

    async def verify(self) -> None:
        return None

    async def close(self) -> None:
        return None


class ScriptedLLM:
    """LLMProvider stand-in returning queued replies; records every request."""

    name = "scripted"
    model = "scripted-1"

    def __init__(self, replies: list[str] | None = None) -> None:
        self.replies = list(replies or [])
        self.requests: list[list[Any]] = []

    async def complete(
        self,
        messages: Any,
        *,
        json_mode: bool = False,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> Any:
        from app.ai.llm import Completion

        self.requests.append(list(messages))
        text = self.replies.pop(0) if self.replies else "{}"
        return Completion(text=text, model=self.model, prompt_tokens=10, completion_tokens=5)
