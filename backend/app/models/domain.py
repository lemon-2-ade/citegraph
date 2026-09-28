"""Source-independent domain records produced by the ingestion pipeline.

Every provider (OpenAlex, Semantic Scholar, the seed dataset, ...) maps its raw payload
into these models. Everything downstream — entity resolution, graph loading — only knows
about these types.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ingestion.normalize import clean_text, normalize_arxiv_id, normalize_doi, normalize_orcid

VenueType = Literal["journal", "conference", "repository", "book", "other"]


class _Record(BaseModel):
    model_config = ConfigDict(frozen=False, str_strip_whitespace=True)


class ExternalIds(_Record):
    doi: str | None = None
    openalex: str | None = None
    arxiv: str | None = None
    s2: str | None = None
    seed: str | None = None

    @field_validator("doi")
    @classmethod
    def _doi(cls, v: str | None) -> str | None:
        return normalize_doi(v)

    @field_validator("arxiv")
    @classmethod
    def _arxiv(cls, v: str | None) -> str | None:
        return normalize_arxiv_id(v)

    def is_empty(self) -> bool:
        return not any((self.doi, self.openalex, self.arxiv, self.s2, self.seed))


class InstitutionRecord(_Record):
    name: str
    country: str | None = None  # ISO 3166-1 alpha-2
    ror: str | None = None
    openalex: str | None = None


class AuthorRecord(_Record):
    name: str
    # Provider-scoped key that asserts identity across papers (e.g. a curated seed key
    # such as "yoshua-bengio"). Resolution treats it like an external identifier.
    key: str | None = None
    orcid: str | None = None
    openalex: str | None = None
    institutions: list[InstitutionRecord] = Field(default_factory=list)

    @field_validator("orcid")
    @classmethod
    def _orcid(cls, v: str | None) -> str | None:
        return normalize_orcid(v)


class VenueRecord(_Record):
    name: str
    type: VenueType = "other"
    openalex: str | None = None


class TopicRecord(_Record):
    name: str
    description: str | None = None
    openalex: str | None = None
    # Provider-assigned relevance of the topic to the paper, in [0, 1] when known.
    score: float | None = Field(default=None, ge=0.0, le=1.0)


class PaperRecord(_Record):
    """A normalised paper as delivered by one source."""

    source: str
    ids: ExternalIds
    title: str
    abstract: str | None = None
    # A curated, non-abstract description (seed dataset only). Never presented as the abstract.
    description: str | None = None
    year: int | None = Field(default=None, ge=1600, le=2100)
    publication_date: date | None = None
    language: str | None = None
    url: str | None = None
    # Only set when the source actually reports it; never estimated.
    citation_count: int | None = Field(default=None, ge=0)
    authors: list[AuthorRecord] = Field(default_factory=list)
    authors_complete: bool = True
    venue: VenueRecord | None = None
    topics: list[TopicRecord] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    # Identifiers of works this paper cites (outgoing CITES edges).
    references: list[ExternalIds] = Field(default_factory=list)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("title", "abstract", "description")
    @classmethod
    def _clean(cls, v: str | None) -> str | None:
        return clean_text(v) if v is not None else None
