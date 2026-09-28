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
    run_readonly_unchecked = read

    async def verify(self) -> None:
        return None

    async def close(self) -> None:
        return None
