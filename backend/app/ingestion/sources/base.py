"""Provider abstraction for external scholarly-metadata sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.models.domain import AuthorRecord, PaperRecord

RawPayload = dict[str, Any]


@dataclass(frozen=True)
class SearchFilters:
    year_from: int | None = None
    year_to: int | None = None


@dataclass
class SourcePage:
    """One page of raw results plus the cursor for the next page (``None`` = done)."""

    items: list[RawPayload]
    next_cursor: str | None
    total: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class PaperSource(ABC):
    """Interface every provider implements.

    Methods return *raw* payloads so the pipeline can persist them before parsing;
    :meth:`parse` turns a raw payload into a validated :class:`PaperRecord`.
    """

    name: str

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        cursor: str | None = None,
        per_page: int = 50,
        filters: SearchFilters | None = None,
    ) -> SourcePage: ...

    @abstractmethod
    async def fetch_paper(self, external_id: str) -> RawPayload | None: ...

    @abstractmethod
    async def fetch_papers(self, external_ids: list[str]) -> list[RawPayload]:
        """Batch lookup; missing IDs are silently absent from the result."""

    @abstractmethod
    async def fetch_citations(
        self, external_id: str, *, cursor: str | None = None, per_page: int = 50
    ) -> SourcePage:
        """Works that cite ``external_id``."""

    @abstractmethod
    async def fetch_authors(self, external_id: str) -> list[AuthorRecord]: ...

    @abstractmethod
    def external_id(self, raw: RawPayload) -> str:
        """The source's own identifier for a raw payload."""

    @abstractmethod
    def parse(self, raw: RawPayload) -> PaperRecord:
        """Map a raw payload to a domain record. Raises ``ValueError`` if unusable."""

    async def aclose(self) -> None:  # noqa: B027 - optional hook
        """Release network resources."""
