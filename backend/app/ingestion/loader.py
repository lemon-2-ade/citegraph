"""Graph construction: resolve a batch of records against Neo4j and write it.

Every write is an idempotent ``MERGE``; re-loading the same batch (e.g. after a crash
between the graph write and the job checkpoint) produces the same graph.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from app.core.logging import get_logger
from app.graph.client import GraphClient
from app.ingestion.normalize import normalize_name, normalize_title, slugify
from app.ingestion.resolution import (
    PAPER_ID_FIELDS,
    AuthorCandidate,
    PaperCandidate,
    PaperResolver,
    author_node_id_for_key,
    dedupe_batch,
    resolve_author,
)
from app.models.domain import (
    AuthorRecord,
    ExternalIds,
    InstitutionRecord,
    PaperRecord,
    VenueRecord,
)

log = get_logger(__name__)


@dataclass
class LoadStats:
    received: int = 0
    duplicates_in_batch: int = 0
    papers_created: int = 0
    papers_matched: int = 0
    papers_merged: int = 0
    id_conflicts: int = 0
    authors_created: int = 0
    authors_matched: int = 0
    citations: int = 0
    stubs_created: int = 0

    def add(self, other: LoadStats) -> None:
        for key, value in asdict(other).items():
            setattr(self, key, getattr(self, key) + value)

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


# --------------------------------------------------------------------------- Cypher
_PAPER_CANDIDATES = """
CALL {
    MATCH (p:Paper) WHERE p.doi IN $doi RETURN p
    UNION
    MATCH (p:Paper) WHERE p.openalex_id IN $openalex RETURN p
    UNION
    MATCH (p:Paper) WHERE p.arxiv_id IN $arxiv RETURN p
    UNION
    MATCH (p:Paper) WHERE p.s2_id IN $s2 RETURN p
    UNION
    MATCH (p:Paper) WHERE p.title_key IN $title_keys RETURN p
}
RETURN p.id AS id, p.doi AS doi, p.openalex_id AS openalex_id, p.arxiv_id AS arxiv_id,
       p.s2_id AS s2_id, p.title_key AS title_key, p.year AS year,
       coalesce(p.is_stub, false) AS is_stub,
       COLLECT { MATCH (a:Author)-[:WROTE]->(p) RETURN a.name } AS author_names
"""

_MERGE_PAPERS = """
MATCH (k:Paper {id: $keep}), (d:Paper {id: $drop})
CALL {
    WITH k, d
    MATCH (d)-[r:CITES]->(t:Paper) WHERE t <> k
    MERGE (k)-[n:CITES]->(t) SET n += properties(r)
}
CALL {
    WITH k, d
    MATCH (s:Paper)-[r:CITES]->(d) WHERE s <> k
    MERGE (s)-[n:CITES]->(k) SET n += properties(r)
}
CALL {
    WITH k, d
    MATCH (a:Author)-[r:WROTE]->(d)
    MERGE (a)-[n:WROTE]->(k) SET n += properties(r)
}
CALL {
    WITH k, d
    MATCH (d)-[r:PUBLISHED_IN]->(v:Venue)
    MERGE (k)-[n:PUBLISHED_IN]->(v) SET n += properties(r)
}
CALL {
    WITH k, d
    MATCH (d)-[r:HAS_TOPIC]->(t:Topic)
    MERGE (k)-[n:HAS_TOPIC]->(t) SET n += properties(r)
}
CALL {
    WITH k, d
    MATCH (d)-[r:HAS_KEYWORD]->(w:Keyword)
    MERGE (k)-[n:HAS_KEYWORD]->(w) SET n += properties(r)
}
WITH k, d, properties(d) AS dp
SET d.doi = null, d.openalex_id = null, d.arxiv_id = null, d.s2_id = null
WITH k, d, dp
SET k.doi = coalesce(k.doi, dp.doi),
    k.openalex_id = coalesce(k.openalex_id, dp.openalex_id),
    k.arxiv_id = coalesce(k.arxiv_id, dp.arxiv_id),
    k.s2_id = coalesce(k.s2_id, dp.s2_id),
    k.title = coalesce(k.title, dp.title),
    k.title_key = coalesce(k.title_key, dp.title_key),
    k.abstract = coalesce(k.abstract, dp.abstract),
    k.description = coalesce(k.description, dp.description),
    k.year = coalesce(k.year, dp.year),
    k.publication_date = coalesce(k.publication_date, dp.publication_date),
    k.url = coalesce(k.url, dp.url),
    k.citation_count = coalesce(k.citation_count, dp.citation_count),
    k.is_stub = coalesce(k.is_stub, false) AND coalesce(dp.is_stub, false),
    k.sources = coalesce(k.sources, []) +
        [s IN coalesce(dp.sources, []) WHERE NOT s IN coalesce(k.sources, [])],
    k.merged_ids = coalesce(k.merged_ids, []) + [d.id],
    k.updated_at = datetime()
DETACH DELETE d
"""

_UPSERT_PAPERS = """
UNWIND $rows AS row
MERGE (p:Paper {id: row.id})
ON CREATE SET p.created_at = datetime()
SET p.title = coalesce(p.title, row.title),
    p.title_key = coalesce(p.title_key, row.title_key),
    p.abstract = coalesce(row.abstract, p.abstract),
    p.description = coalesce(p.description, row.description),
    p.year = coalesce(p.year, row.year),
    p.publication_date = coalesce(p.publication_date, date(row.publication_date)),
    p.doi = coalesce(p.doi, row.doi),
    p.openalex_id = coalesce(p.openalex_id, row.openalex_id),
    p.arxiv_id = coalesce(p.arxiv_id, row.arxiv_id),
    p.s2_id = coalesce(p.s2_id, row.s2_id),
    p.url = coalesce(p.url, row.url),
    p.language = coalesce(p.language, row.language),
    p.citation_count = coalesce(row.citation_count, p.citation_count),
    p.authors_complete = coalesce(p.authors_complete, false) OR row.authors_complete,
    p.is_stub = false,
    p.sources = CASE WHEN row.source IN coalesce(p.sources, []) THEN p.sources
                     ELSE coalesce(p.sources, []) + row.source END,
    p.updated_at = datetime()
"""

_AUTHOR_CANDIDATES = """
CALL {
    MATCH (a:Author) WHERE a.id IN $ids RETURN a
    UNION
    MATCH (a:Author) WHERE a.orcid IN $orcid RETURN a
    UNION
    MATCH (a:Author) WHERE a.openalex_id IN $openalex RETURN a
    UNION
    MATCH (a:Author) WHERE a.name_key IN $name_keys RETURN a
}
RETURN a.id AS id, a.name_key AS name_key, a.orcid AS orcid, a.openalex_id AS openalex_id,
       COLLECT {
           MATCH (a)-[:WROTE]->(:Paper)<-[:WROTE]-(c:Author) WHERE c <> a
           RETURN DISTINCT c.name_key
       } AS coauthor_keys
"""

_EXISTING_PAPER_AUTHORS = """
MATCH (a:Author)-[:WROTE]->(p:Paper) WHERE p.id IN $paper_ids
RETURN p.id AS paper_id, a.id AS id, a.name_key AS name_key
"""

_UPSERT_AUTHORS = """
UNWIND $rows AS row
MERGE (a:Author {id: row.id})
ON CREATE SET a.created_at = datetime()
SET a.name = coalesce(a.name, row.name),
    a.name_key = coalesce(a.name_key, row.name_key),
    a.orcid = coalesce(a.orcid, row.orcid),
    a.openalex_id = coalesce(a.openalex_id, row.openalex_id),
    a.updated_at = datetime()
"""

_WROTE = """
UNWIND $rows AS row
MATCH (a:Author {id: row.author_id}), (p:Paper {id: row.paper_id})
MERGE (a)-[w:WROTE]->(p)
SET w.position = row.position, w.source = row.source
"""

_AFFILIATIONS = """
UNWIND $rows AS row
MERGE (i:Institution {id: row.id})
SET i.name = coalesce(i.name, row.name),
    i.country = coalesce(i.country, row.country),
    i.ror = coalesce(i.ror, row.ror)
WITH i, row
MATCH (a:Author {id: row.author_id})
MERGE (a)-[r:AFFILIATED_WITH]->(i)
SET r.source = row.source
"""

_VENUES = """
UNWIND $rows AS row
MERGE (v:Venue {id: row.id})
SET v.name = coalesce(v.name, row.name), v.type = coalesce(v.type, row.type)
WITH v, row
MATCH (p:Paper {id: row.paper_id})
MERGE (p)-[r:PUBLISHED_IN]->(v)
SET r.source = row.source
"""

_TOPICS = """
UNWIND $rows AS row
MERGE (t:Topic {id: row.id})
SET t.name = coalesce(t.name, row.name),
    t.description = coalesce(t.description, row.description),
    t.openalex_id = coalesce(t.openalex_id, row.openalex_id)
WITH t, row
MATCH (p:Paper {id: row.paper_id})
MERGE (p)-[r:HAS_TOPIC]->(t)
SET r.score = coalesce(row.score, r.score), r.source = row.source
"""

_KEYWORDS = """
UNWIND $rows AS row
MERGE (k:Keyword {id: row.id})
SET k.name = coalesce(k.name, row.name)
WITH k, row
MATCH (p:Paper {id: row.paper_id})
MERGE (p)-[r:HAS_KEYWORD]->(k)
SET r.source = row.source
"""

_STUBS = """
UNWIND $rows AS row
MERGE (p:Paper {id: row.id})
ON CREATE SET p.is_stub = true,
              p.created_at = datetime(),
              p.doi = row.doi,
              p.openalex_id = row.openalex_id,
              p.arxiv_id = row.arxiv_id,
              p.s2_id = row.s2_id,
              p.sources = [row.source]
"""

_CITES = """
UNWIND $rows AS row
MATCH (a:Paper {id: row.src}), (b:Paper {id: row.dst})
MERGE (a)-[c:CITES]->(b)
ON CREATE SET c.created_at = datetime(), c.source = row.source, c.confidence = row.confidence
RETURN count(c) AS n
"""


# --------------------------------------------------------------------------- helpers
def new_paper_id() -> str:
    return f"paper:{uuid.uuid4()}"


def new_author_id() -> str:
    return f"author:{uuid.uuid4()}"


def venue_id(venue: VenueRecord) -> str:
    return f"venue:{venue.openalex}" if venue.openalex else f"venue:{slugify(venue.name)}"


def institution_id(inst: InstitutionRecord) -> str:
    if inst.ror:
        return f"institution:ror:{inst.ror.rstrip('/').rsplit('/', 1)[-1]}"
    if inst.openalex:
        return f"institution:{inst.openalex}"
    suffix = f"-{inst.country.lower()}" if inst.country else ""
    return f"institution:{slugify(inst.name)}{suffix}"


def topic_id(name: str) -> str:
    return f"topic:{slugify(name)}"


def keyword_id(name: str) -> str:
    return f"keyword:{slugify(name)}"


def _ids_payload(ids: ExternalIds) -> dict[str, str | None]:
    return {prop: getattr(ids, attr) for attr, prop in PAPER_ID_FIELDS}


def _candidate(row: dict[str, Any]) -> PaperCandidate:
    from app.ingestion.normalize import author_key

    return PaperCandidate(
        id=row["id"],
        doi=row["doi"],
        openalex_id=row["openalex_id"],
        arxiv_id=row["arxiv_id"],
        s2_id=row["s2_id"],
        title_key=row["title_key"],
        year=row["year"],
        is_stub=row["is_stub"],
        author_keys=frozenset(author_key(n) for n in row["author_names"] if n),
    )


# --------------------------------------------------------------------------- loader
class GraphLoader:
    def __init__(self, graph: GraphClient, resolver: PaperResolver | None = None) -> None:
        self._graph = graph
        self._resolver = resolver or PaperResolver()

    async def load(self, records: Sequence[PaperRecord]) -> LoadStats:
        stats = LoadStats(received=len(records))
        batch = dedupe_batch(records, self._resolver)
        stats.duplicates_in_batch = len(records) - len(batch)
        if not batch:
            return stats

        assigned = await self._resolve_papers(batch, stats)
        await self._write_papers(batch, assigned)
        author_ids = await self._resolve_and_write_authors(batch, assigned, stats)
        await self._write_vocabulary(batch, assigned, author_ids)
        await self._write_citations(batch, assigned, stats)
        log.info("ingestion.batch_loaded", **stats.as_dict())
        return stats

    async def _paper_candidates(
        self, id_sets: Iterable[ExternalIds], title_keys: Iterable[str] = ()
    ) -> list[PaperCandidate]:
        params: dict[str, list[str]] = {"doi": [], "openalex": [], "arxiv": [], "s2": []}
        for ids in id_sets:
            for attr in params:
                value = getattr(ids, attr)
                if value:
                    params[attr].append(value)
        rows = await self._graph.read(
            _PAPER_CANDIDATES,
            {**params, "title_keys": sorted(set(title_keys))},
            label="loader.paper_candidates",
        )
        return [_candidate(r) for r in rows]

    async def _resolve_papers(self, batch: list[PaperRecord], stats: LoadStats) -> list[str]:
        candidates = await self._paper_candidates(
            (r.ids for r in batch), (normalize_title(r.title) for r in batch)
        )
        owner = {
            (prop, c.identifier(prop)): c.id
            for c in candidates
            for _, prop in PAPER_ID_FIELDS
            if c.identifier(prop)
        }
        assigned: list[str] = []
        for record in batch:
            match = self._resolver.resolve(record, candidates)
            for drop in match.merge_ids:
                keep = match.paper_id
                assert keep is not None  # merges only accompany an identifier match
                await self._graph.write(
                    _MERGE_PAPERS, {"keep": keep, "drop": drop}, label="loader.merge"
                )
                stats.papers_merged += 1
                candidates = [c for c in candidates if c.id != drop]
                owner = {k: (keep if v == drop else v) for k, v in owner.items()}
            if match.conflicts:
                stats.id_conflicts += len(match.conflicts)
                log.warning("ingestion.id_conflict", title=record.title, conflicts=match.conflicts)
            paper_id = match.paper_id or new_paper_id()
            if match.is_new:
                stats.papers_created += 1
            else:
                stats.papers_matched += 1
            # Never write an identifier another node already owns (uniqueness constraint);
            # the conflict has been logged above.
            for attr, prop in PAPER_ID_FIELDS:
                value = getattr(record.ids, attr)
                if value and owner.get((prop, value), paper_id) != paper_id:
                    setattr(record.ids, attr, None)
            assigned.append(paper_id)
        return assigned

    async def _write_papers(self, batch: list[PaperRecord], assigned: list[str]) -> None:
        rows = []
        for record, paper_id in zip(batch, assigned, strict=True):
            rows.append(
                {
                    "id": paper_id,
                    "title": record.title,
                    "title_key": normalize_title(record.title),
                    "abstract": record.abstract,
                    "description": record.description,
                    "year": record.year,
                    "publication_date": record.publication_date.isoformat()
                    if record.publication_date
                    else None,
                    "url": record.url,
                    "language": record.language,
                    "citation_count": record.citation_count,
                    "authors_complete": record.authors_complete,
                    "source": record.source,
                    **_ids_payload(record.ids),
                }
            )
        await self._graph.write(_UPSERT_PAPERS, {"rows": rows}, label="loader.papers")

    async def _resolve_and_write_authors(
        self, batch: list[PaperRecord], assigned: list[str], stats: LoadStats
    ) -> dict[tuple[int, int], str]:
        all_authors = [a for r in batch for a in r.authors]
        cand_rows = await self._graph.read(
            _AUTHOR_CANDIDATES,
            {
                "ids": [author_node_id_for_key(a.key) for a in all_authors if a.key],
                "orcid": [a.orcid for a in all_authors if a.orcid],
                "openalex": [a.openalex for a in all_authors if a.openalex],
                "name_keys": sorted({normalize_name(a.name) for a in all_authors}),
            },
            label="loader.author_candidates",
        )
        candidates = [
            AuthorCandidate(
                id=r["id"],
                name_key=r["name_key"] or "",
                orcid=r["orcid"],
                openalex_id=r["openalex_id"],
                coauthor_keys=frozenset(k for k in r["coauthor_keys"] if k),
            )
            for r in cand_rows
        ]
        existing_rows = await self._graph.read(
            _EXISTING_PAPER_AUTHORS, {"paper_ids": assigned}, label="loader.paper_authors"
        )
        on_paper: dict[str, dict[str, str]] = defaultdict(dict)
        for r in existing_rows:
            if r["name_key"]:
                on_paper[r["paper_id"]][r["name_key"]] = r["id"]

        result: dict[tuple[int, int], str] = {}
        author_rows: dict[str, dict[str, Any]] = {}
        wrote_rows: list[dict[str, Any]] = []
        for p_index, (record, paper_id) in enumerate(zip(batch, assigned, strict=True)):
            names = [a.name for a in record.authors]
            for a_index, author in enumerate(record.authors):
                name_key = normalize_name(author.name)
                author_id: str | None = on_paper[paper_id].get(name_key)
                if author_id is None:
                    author_id, _reason = resolve_author(author, names, candidates)
                if author_id is None:
                    author_id = (
                        author_node_id_for_key(author.key) if author.key else new_author_id()
                    )
                    stats.authors_created += 1
                    # Make the new author resolvable by later papers in this batch.
                    candidates.append(
                        AuthorCandidate(
                            id=author_id,
                            name_key=name_key,
                            orcid=author.orcid,
                            openalex_id=author.openalex,
                            coauthor_keys=frozenset(normalize_name(n) for n in names) - {name_key},
                        )
                    )
                else:
                    stats.authors_matched += 1
                result[(p_index, a_index)] = author_id
                author_rows.setdefault(author_id, self._author_row(author_id, author))
                wrote_rows.append(
                    {
                        "author_id": author_id,
                        "paper_id": paper_id,
                        "position": a_index + 1,
                        "source": record.source,
                    }
                )
        await self._graph.write(
            _UPSERT_AUTHORS, {"rows": list(author_rows.values())}, label="loader.authors"
        )
        await self._graph.write(_WROTE, {"rows": wrote_rows}, label="loader.wrote")
        return result

    @staticmethod
    def _author_row(author_id: str, author: AuthorRecord) -> dict[str, Any]:
        return {
            "id": author_id,
            "name": author.name,
            "name_key": normalize_name(author.name),
            "orcid": author.orcid,
            "openalex_id": author.openalex,
        }

    async def _write_vocabulary(
        self,
        batch: list[PaperRecord],
        assigned: list[str],
        author_ids: dict[tuple[int, int], str],
    ) -> None:
        venues, topics, keywords, affiliations = [], [], [], []
        for p_index, (record, paper_id) in enumerate(zip(batch, assigned, strict=True)):
            if record.venue:
                venues.append(
                    {
                        "id": venue_id(record.venue),
                        "name": record.venue.name,
                        "type": record.venue.type,
                        "paper_id": paper_id,
                        "source": record.source,
                    }
                )
            for topic in record.topics:
                topics.append(
                    {
                        "id": topic_id(topic.name),
                        "name": topic.name,
                        "description": topic.description,
                        "openalex_id": topic.openalex,
                        "score": topic.score,
                        "paper_id": paper_id,
                        "source": record.source,
                    }
                )
            for keyword in record.keywords:
                if slugify(keyword):
                    keywords.append(
                        {
                            "id": keyword_id(keyword),
                            "name": keyword,
                            "paper_id": paper_id,
                            "source": record.source,
                        }
                    )
            for a_index, author in enumerate(record.authors):
                for inst in author.institutions:
                    affiliations.append(
                        {
                            "id": institution_id(inst),
                            "name": inst.name,
                            "country": inst.country,
                            "ror": inst.ror,
                            "author_id": author_ids[(p_index, a_index)],
                            "source": record.source,
                        }
                    )
        for query, rows, label in (
            (_VENUES, venues, "loader.venues"),
            (_TOPICS, topics, "loader.topics"),
            (_KEYWORDS, keywords, "loader.keywords"),
            (_AFFILIATIONS, affiliations, "loader.affiliations"),
        ):
            if rows:
                await self._graph.write(query, {"rows": rows}, label=label)

    async def _write_citations(
        self, batch: list[PaperRecord], assigned: list[str], stats: LoadStats
    ) -> None:
        refs = [ref for record in batch for ref in record.references if not ref.is_empty()]
        if not refs:
            return
        candidates = await self._paper_candidates(refs)
        index: dict[tuple[str, str], str] = {}
        # Papers of this batch first: they were just written, so they resolve directly.
        for record, paper_id in zip(batch, assigned, strict=True):
            for attr, prop in PAPER_ID_FIELDS:
                value = getattr(record.ids, attr)
                if value:
                    index[(prop, value)] = paper_id
        for cand in candidates:
            for _, prop in PAPER_ID_FIELDS:
                value = cand.identifier(prop)
                if value:
                    index[(prop, value)] = cand.id

        stubs: dict[str, dict[str, Any]] = {}
        edges: set[tuple[str, str, str]] = set()
        for record, paper_id in zip(batch, assigned, strict=True):
            for ref in record.references:
                if ref.is_empty():
                    continue
                keys = [(prop, getattr(ref, attr)) for attr, prop in PAPER_ID_FIELDS]
                keys = [(p, v) for p, v in keys if v]
                target = next((index[k] for k in keys if k in index), None)
                if target is None:
                    target = new_paper_id()
                    stubs[target] = {
                        "id": target,
                        "source": record.source,
                        **_ids_payload(ref),
                    }
                    for key in keys:
                        index[key] = target
                if target != paper_id:
                    edges.add((paper_id, target, record.source))

        if stubs:
            await self._graph.write(_STUBS, {"rows": list(stubs.values())}, label="loader.stubs")
            stats.stubs_created += len(stubs)
        rows = [
            {"src": s, "dst": d, "source": src, "confidence": 1.0} for s, d, src in sorted(edges)
        ]
        await self._graph.write(_CITES, {"rows": rows}, label="loader.cites")
        stats.citations += len(rows)
