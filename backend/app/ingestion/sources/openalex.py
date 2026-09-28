"""OpenAlex provider (https://docs.openalex.org).

OpenAlex is the primary source: open, no API key, and it exposes references
(``referenced_works``), authorships with institutions, venues and topics for each work.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import httpx

from app.core.config import Settings
from app.ingestion.http import HttpFetcher, RateLimiter
from app.ingestion.normalize import normalize_arxiv_id
from app.ingestion.sources.base import PaperSource, RawPayload, SearchFilters, SourcePage
from app.models.domain import (
    AuthorRecord,
    ExternalIds,
    InstitutionRecord,
    PaperRecord,
    TopicRecord,
    VenueRecord,
    VenueType,
)

_OA_ID = re.compile(r"([WASITCVP]\d+)$", re.IGNORECASE)
_ARXIV_URL = re.compile(r"arxiv\.org/(?:abs|pdf)/([^\s?#]+)", re.IGNORECASE)
_ARXIV_DOI = re.compile(r"^10\.48550/arxiv\.(.+)$", re.IGNORECASE)

_SELECT = ",".join(
    [
        "id",
        "doi",
        "title",
        "display_name",
        "publication_year",
        "publication_date",
        "language",
        "type",
        "cited_by_count",
        "abstract_inverted_index",
        "authorships",
        "primary_location",
        "locations",
        "topics",
        "keywords",
        "referenced_works",
        "ids",
    ]
)

_VENUE_TYPES: dict[str, VenueType] = {
    "journal": "journal",
    "conference": "conference",
    "repository": "repository",
    "ebook platform": "book",
    "book series": "book",
}

BATCH_LOOKUP_SIZE = 50  # OpenAlex allows OR-filters of up to 100 values; stay well below.


def short_id(value: str | None) -> str | None:
    """``https://openalex.org/W123`` -> ``W123``."""
    if not value:
        return None
    match = _OA_ID.search(value.strip())
    return match.group(1).upper() if match else None


def reconstruct_abstract(inverted: dict[str, list[int]] | None) -> str | None:
    """OpenAlex ships abstracts as an inverted index (word -> positions)."""
    if not inverted:
        return None
    positions: dict[int, str] = {}
    for word, indexes in inverted.items():
        for index in indexes:
            positions[index] = word
    if not positions:
        return None
    return " ".join(positions[i] for i in sorted(positions))


def extract_arxiv_id(work: dict[str, Any]) -> str | None:
    doi = (work.get("doi") or "").lower().removeprefix("https://doi.org/")
    match = _ARXIV_DOI.match(doi)
    if match:
        return normalize_arxiv_id(match.group(1))
    for location in work.get("locations") or []:
        for key in ("landing_page_url", "pdf_url"):
            url = location.get(key) or ""
            match = _ARXIV_URL.search(url)
            if match:
                arxiv = normalize_arxiv_id(match.group(1).removesuffix(".pdf"))
                if arxiv:
                    return arxiv
    return None


class OpenAlexSource(PaperSource):
    name = "openalex"
    id_field = "openalex"

    def __init__(self, fetcher: HttpFetcher, base_url: str, mailto: str | None = None) -> None:
        self._fetcher = fetcher
        self._base = base_url.rstrip("/")
        self._mailto = mailto
        self._client: httpx.AsyncClient | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> OpenAlexSource:
        user_agent = "ResearchGraph/0.1"
        if settings.openalex_mailto:
            user_agent += f" (mailto:{settings.openalex_mailto})"
        client = httpx.AsyncClient(
            timeout=settings.http_timeout_seconds, headers={"User-Agent": user_agent}
        )
        fetcher = HttpFetcher(
            client,
            RateLimiter(settings.openalex_requests_per_second),
            max_attempts=settings.http_max_retries,
        )
        source = cls(fetcher, settings.openalex_base_url, settings.openalex_mailto)
        source._client = client
        return source

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    # -- requests ---------------------------------------------------------------
    def _params(self, **extra: Any) -> dict[str, Any]:
        params: dict[str, Any] = {"select": _SELECT}
        if self._mailto:
            params["mailto"] = self._mailto
        params.update({k: v for k, v in extra.items() if v is not None})
        return params

    async def _page(self, params: dict[str, Any]) -> SourcePage:
        data = await self._fetcher.get_json(f"{self._base}/works", params)
        if not data:
            return SourcePage(items=[], next_cursor=None)
        meta = data.get("meta") or {}
        items = data.get("results") or []
        # OpenAlex keeps returning a cursor on the last page; an empty page ends paging.
        next_cursor = meta.get("next_cursor") if items else None
        return SourcePage(items=items, next_cursor=next_cursor, total=meta.get("count"), meta=meta)

    async def search(
        self,
        query: str,
        *,
        cursor: str | None = None,
        per_page: int = 50,
        filters: SearchFilters | None = None,
    ) -> SourcePage:
        clauses = []
        if filters and filters.year_from:
            clauses.append(f"from_publication_date:{filters.year_from}-01-01")
        if filters and filters.year_to:
            clauses.append(f"to_publication_date:{filters.year_to}-12-31")
        params = self._params(
            search=query,
            filter=",".join(clauses) or None,
            cursor=cursor or "*",
            **{"per-page": min(max(per_page, 1), 200)},
        )
        return await self._page(params)

    async def fetch_paper(self, external_id: str) -> RawPayload | None:
        key = short_id(external_id) or external_id  # also accepts "doi:10.x/..." keys
        data = await self._fetcher.get_json(f"{self._base}/works/{key}", self._params())
        return data if isinstance(data, dict) else None

    async def fetch_papers(self, external_ids: list[str]) -> list[RawPayload]:
        results: list[RawPayload] = []
        ids = [i for i in (short_id(x) for x in external_ids) if i]
        for start in range(0, len(ids), BATCH_LOOKUP_SIZE):
            chunk = ids[start : start + BATCH_LOOKUP_SIZE]
            page = await self._page(
                self._params(filter=f"openalex:{'|'.join(chunk)}", **{"per-page": len(chunk)})
            )
            results.extend(page.items)
        return results

    async def fetch_citations(
        self, external_id: str, *, cursor: str | None = None, per_page: int = 50
    ) -> SourcePage:
        oa_id = short_id(external_id)
        if oa_id is None:
            raise ValueError(f"Not an OpenAlex work id: {external_id!r}")
        return await self._page(
            self._params(
                filter=f"cites:{oa_id}",
                cursor=cursor or "*",
                **{"per-page": min(max(per_page, 1), 200)},
            )
        )

    async def fetch_authors(self, external_id: str) -> list[AuthorRecord]:
        raw = await self.fetch_paper(external_id)
        return self.parse(raw).authors if raw else []

    # -- parsing ----------------------------------------------------------------
    def external_id(self, raw: RawPayload) -> str:
        oa_id = short_id(raw.get("id"))
        if not oa_id:
            raise ValueError("OpenAlex work without id")
        return oa_id

    def parse(self, raw: RawPayload) -> PaperRecord:
        title = raw.get("title") or raw.get("display_name")
        if not title:
            raise ValueError(f"OpenAlex work {raw.get('id')} has no title")

        authors = []
        for authorship in raw.get("authorships") or []:
            author = authorship.get("author") or {}
            name = author.get("display_name") or authorship.get("raw_author_name")
            if not name:
                continue
            institutions = [
                InstitutionRecord(
                    name=inst["display_name"],
                    country=inst.get("country_code"),
                    ror=inst.get("ror"),
                    openalex=short_id(inst.get("id")),
                )
                for inst in authorship.get("institutions") or []
                if inst.get("display_name")
            ]
            authors.append(
                AuthorRecord(
                    name=name,
                    orcid=author.get("orcid"),
                    openalex=short_id(author.get("id")),
                    institutions=institutions,
                )
            )

        venue = None
        source = (raw.get("primary_location") or {}).get("source") or {}
        if source.get("display_name"):
            venue = VenueRecord(
                name=source["display_name"],
                type=_VENUE_TYPES.get((source.get("type") or "").lower(), "other"),
                openalex=short_id(source.get("id")),
            )

        topics = [
            TopicRecord(
                name=t["display_name"],
                openalex=short_id(t.get("id")),
                score=t.get("score"),
            )
            for t in raw.get("topics") or []
            if t.get("display_name")
        ]
        keywords = [k["display_name"] for k in raw.get("keywords") or [] if k.get("display_name")]

        publication_date = None
        if raw.get("publication_date"):
            try:
                publication_date = date.fromisoformat(raw["publication_date"])
            except ValueError:
                publication_date = None

        landing = (raw.get("primary_location") or {}).get("landing_page_url")
        return PaperRecord(
            source=self.name,
            ids=ExternalIds(
                doi=raw.get("doi"),
                openalex=self.external_id(raw),
                arxiv=extract_arxiv_id(raw),
            ),
            title=title,
            abstract=reconstruct_abstract(raw.get("abstract_inverted_index")),
            year=raw.get("publication_year"),
            publication_date=publication_date,
            language=raw.get("language"),
            url=landing or raw.get("doi"),
            citation_count=raw.get("cited_by_count"),
            authors=authors,
            venue=venue,
            topics=topics,
            keywords=keywords,
            references=[
                ExternalIds(openalex=oa)
                for oa in (short_id(r) for r in raw.get("referenced_works") or [])
                if oa
            ],
        )
