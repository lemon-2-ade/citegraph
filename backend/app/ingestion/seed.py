"""Curated seed dataset (``data/seed/papers.json``).

Lets the application run and be demonstrated without any external API. The dataset is
validated on load; its provenance and limitations are documented inside the file and in
docs/ingestion.md. Seed papers carry a ``seed_key`` identifier so they can cite each
other even when they have no arXiv ID, and so later OpenAlex ingestion can merge into
them by arXiv ID or by title/year/author matching.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.logging import get_logger
from app.graph.client import GraphClient
from app.ingestion.loader import GraphLoader, LoadStats
from app.ingestion.normalize import slugify
from app.models.domain import AuthorRecord, ExternalIds, PaperRecord, TopicRecord, VenueRecord

log = get_logger(__name__)

DEFAULT_SEED_PATH = Path(__file__).resolve().parents[3] / "data" / "seed" / "papers.json"
SOURCE_NAME = "seed"


class SeedAuthor(BaseModel):
    name: str
    key: str


class SeedTopic(BaseModel):
    key: str
    name: str
    description: str | None = None


class SeedVenue(BaseModel):
    key: str
    name: str
    type: Literal["journal", "conference", "repository", "book", "other"]


class SeedPaper(BaseModel):
    key: str
    title: str
    year: int
    arxiv: str | None = None
    venue: str
    authors: list[str | SeedAuthor]
    authors_complete: bool = True
    topics: list[str]
    keywords: list[str] = Field(default_factory=list)
    description: str
    cites: list[str] = Field(default_factory=list)

    def author_records(self) -> list[AuthorRecord]:
        records = []
        for author in self.authors:
            if isinstance(author, SeedAuthor):
                records.append(AuthorRecord(name=author.name, key=author.key))
            else:
                records.append(AuthorRecord(name=author, key=slugify(author)))
        return records


class SeedDataset(BaseModel):
    dataset: str
    version: int
    description: str
    provenance: dict[str, str]
    topics: list[SeedTopic]
    venues: list[SeedVenue]
    papers: list[SeedPaper]

    @model_validator(mode="after")
    def _referential_integrity(self) -> SeedDataset:
        keys = [p.key for p in self.papers]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate paper keys in seed dataset")
        by_key = {p.key: p for p in self.papers}
        topics = {t.key for t in self.topics}
        venues = {v.key for v in self.venues}
        for paper in self.papers:
            if paper.venue not in venues:
                raise ValueError(f"{paper.key}: unknown venue {paper.venue!r}")
            unknown_topics = set(paper.topics) - topics
            if unknown_topics:
                raise ValueError(f"{paper.key}: unknown topics {sorted(unknown_topics)}")
            for cited in paper.cites:
                target = by_key.get(cited)
                if target is None:
                    raise ValueError(f"{paper.key}: cites unknown paper {cited!r}")
                if target.year > paper.year:
                    raise ValueError(f"{paper.key} ({paper.year}) cites later paper {cited}")
                if cited == paper.key:
                    raise ValueError(f"{paper.key} cites itself")
        return self


def load_dataset(path: Path = DEFAULT_SEED_PATH) -> SeedDataset:
    return SeedDataset.model_validate(json.loads(path.read_text(encoding="utf-8")))


def to_records(dataset: SeedDataset) -> list[PaperRecord]:
    topics = {t.key: t for t in dataset.topics}
    venues = {v.key: v for v in dataset.venues}
    by_key = {p.key: p for p in dataset.papers}
    records = []
    for paper in dataset.papers:
        venue = venues[paper.venue]
        records.append(
            PaperRecord(
                source=SOURCE_NAME,
                ids=ExternalIds(arxiv=paper.arxiv, seed=paper.key),
                title=paper.title,
                description=paper.description,
                year=paper.year,
                url=f"https://arxiv.org/abs/{paper.arxiv}" if paper.arxiv else None,
                authors=paper.author_records(),
                authors_complete=paper.authors_complete,
                venue=VenueRecord(name=venue.name, type=venue.type),
                topics=[
                    TopicRecord(name=topics[t].name, description=topics[t].description)
                    for t in paper.topics
                ],
                keywords=paper.keywords,
                references=[
                    ExternalIds(seed=cited, arxiv=by_key[cited].arxiv) for cited in paper.cites
                ],
            )
        )
    return records


async def seed_graph(
    graph: GraphClient, path: Path = DEFAULT_SEED_PATH, *, batch_size: int = 50
) -> LoadStats:
    dataset = load_dataset(path)
    records = to_records(dataset)
    loader = GraphLoader(graph)
    total = LoadStats()
    for start in range(0, len(records), batch_size):
        total.add(await loader.load(records[start : start + batch_size]))
    log.info("seed.loaded", dataset=dataset.dataset, version=dataset.version, **total.as_dict())
    return total
