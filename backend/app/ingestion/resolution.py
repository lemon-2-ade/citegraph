"""Entity resolution for papers and authors.

Scholarly metadata is full of duplicates: the same work appears as a preprint and a
published version, with differently cased titles, truncated author lists, or only some
identifiers. Resolution here is deliberately **conservative** — a wrong merge corrupts
the citation graph, whereas a missed merge only leaves a duplicate that a later run
(with more identifiers) can merge.

Papers
    1. Any shared persistent identifier (DOI, OpenAlex, arXiv, Semantic Scholar) is a
       match. If identifiers point at *several* existing nodes, they are the same work
       and are scheduled for merging — unless two of them carry conflicting values of
       the same identifier type, which is reported instead of merged.
    2. Otherwise a fuzzy match requires ALL of: title similarity >= threshold, years
       within a tolerance, compatible identifiers, and either author-list overlap above a
       threshold or (when author lists are unavailable) a near-exact title with both
       years known.
Authors
    ORCID / OpenAlex ID / curated key match directly; a bare name only matches an
    existing author with the same normalised name *who shares a co-author* with the
    incoming paper. Common names without that evidence stay separate.

Everything in this module is pure (no I/O) so it can be tested exhaustively.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from app.ingestion.normalize import author_key, normalize_name, normalize_title
from app.models.domain import AuthorRecord, ExternalIds, PaperRecord, TopicRecord

# (ExternalIds attribute, graph property) in decreasing order of reliability.
PAPER_ID_FIELDS: tuple[tuple[str, str], ...] = (
    ("doi", "doi"),
    ("openalex", "openalex_id"),
    ("arxiv", "arxiv_id"),
    ("s2", "s2_id"),
    # Curated seed-dataset key: lets seed papers without external IDs reference each other.
    ("seed", "seed_key"),
)


@dataclass(frozen=True)
class PaperCandidate:
    """An existing graph paper, reduced to what resolution needs."""

    id: str
    doi: str | None = None
    openalex_id: str | None = None
    arxiv_id: str | None = None
    s2_id: str | None = None
    seed_key: str | None = None
    title_key: str | None = None
    year: int | None = None
    author_keys: frozenset[str] = frozenset()
    is_stub: bool = False

    def identifier(self, prop: str) -> str | None:
        value: str | None = getattr(self, prop)
        return value


@dataclass
class PaperMatch:
    paper_id: str | None
    reason: str
    score: float | None = None
    # Other existing nodes that are the same work and should be merged into ``paper_id``.
    merge_ids: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    @property
    def is_new(self) -> bool:
        return self.paper_id is None


def title_similarity(a: str, b: str) -> float:
    return fuzz.ratio(normalize_title(a), normalize_title(b)) / 100.0


def author_overlap(a: Iterable[str], b: Iterable[str]) -> float | None:
    """Overlap coefficient |A∩B| / min(|A|,|B|); robust to truncated author lists."""
    set_a, set_b = {k for k in a if k}, {k for k in b if k}
    if not set_a or not set_b:
        return None
    return len(set_a & set_b) / min(len(set_a), len(set_b))


def record_author_keys(record: PaperRecord) -> frozenset[str]:
    return frozenset(k for k in (author_key(a.name) for a in record.authors) if k)


def _conflicting_ids(record_ids: ExternalIds, candidate: PaperCandidate) -> list[str]:
    conflicts = []
    for attr, prop in PAPER_ID_FIELDS:
        mine, theirs = getattr(record_ids, attr), candidate.identifier(prop)
        if mine and theirs and mine != theirs:
            conflicts.append(prop)
    return conflicts


@dataclass(frozen=True)
class ResolutionConfig:
    title_threshold: float = 0.95
    exact_title_threshold: float = 0.99
    author_threshold: float = 0.5
    year_tolerance: int = 1  # preprint vs. published version


class PaperResolver:
    def __init__(self, config: ResolutionConfig | None = None) -> None:
        self.config = config or ResolutionConfig()

    def resolve(self, record: PaperRecord, candidates: Sequence[PaperCandidate]) -> PaperMatch:
        by_id = self._identifier_matches(record, candidates)
        if by_id:
            return by_id
        return self._fuzzy_match(record, candidates) or PaperMatch(paper_id=None, reason="new")

    def _identifier_matches(
        self, record: PaperRecord, candidates: Sequence[PaperCandidate]
    ) -> PaperMatch | None:
        matched: dict[str, tuple[int, PaperCandidate, str]] = {}
        for rank, (attr, prop) in enumerate(PAPER_ID_FIELDS):
            value = getattr(record.ids, attr)
            if not value:
                continue
            for cand in candidates:
                if cand.identifier(prop) == value and cand.id not in matched:
                    matched[cand.id] = (rank, cand, prop)
        if not matched:
            return None

        # Canonical node: a real (non-stub) node first, then the strongest identifier,
        # then the smallest id for determinism.
        ordered = sorted(matched.values(), key=lambda m: (m[1].is_stub, m[0], m[1].id))
        _, canonical, prop = ordered[0]
        match = PaperMatch(paper_id=canonical.id, reason=prop, score=1.0)
        for _, other, _ in ordered[1:]:
            clash = _pairwise_conflicts(canonical, other)
            if clash:
                match.conflicts.append(f"{other.id} conflicts on {','.join(clash)}")
            else:
                match.merge_ids.append(other.id)
        return match

    def _fuzzy_match(
        self, record: PaperRecord, candidates: Sequence[PaperCandidate]
    ) -> PaperMatch | None:
        cfg = self.config
        record_title = normalize_title(record.title)
        record_authors = record_author_keys(record)
        best: PaperMatch | None = None
        for cand in candidates:
            if cand.is_stub or not cand.title_key:
                continue
            if _conflicting_ids(record.ids, cand):
                continue
            similarity = fuzz.ratio(record_title, cand.title_key) / 100.0
            if similarity < cfg.title_threshold:
                continue
            if record.year and cand.year and abs(record.year - cand.year) > cfg.year_tolerance:
                continue
            overlap = author_overlap(record_authors, cand.author_keys)
            if overlap is not None:
                if overlap < cfg.author_threshold:
                    continue
                score = 0.6 * similarity + 0.4 * overlap
            else:
                both_years = record.year is not None and cand.year is not None
                if similarity < cfg.exact_title_threshold or not both_years:
                    continue
                score = 0.8 * similarity
            if best is None or (best.score or 0) < score:
                best = PaperMatch(paper_id=cand.id, reason="title+year+authors", score=score)
        return best


def _pairwise_conflicts(a: PaperCandidate, b: PaperCandidate) -> list[str]:
    return [
        prop
        for _, prop in PAPER_ID_FIELDS
        if a.identifier(prop) and b.identifier(prop) and a.identifier(prop) != b.identifier(prop)
    ]


# --------------------------------------------------------------------------- batches
def merge_records(primary: PaperRecord, other: PaperRecord) -> PaperRecord:
    """Combine two records of the same work, preferring ``primary``'s non-null values."""
    data = primary.model_copy(deep=True)
    for attr, _ in PAPER_ID_FIELDS:
        if not getattr(data.ids, attr) and getattr(other.ids, attr):
            setattr(data.ids, attr, getattr(other.ids, attr))
    for name in (
        "abstract",
        "description",
        "year",
        "publication_date",
        "language",
        "url",
        "citation_count",
        "venue",
    ):
        if getattr(data, name) is None and getattr(other, name) is not None:
            setattr(data, name, getattr(other, name))
    if len(other.authors) > len(data.authors):
        data.authors = list(other.authors)
        data.authors_complete = other.authors_complete
    seen_topics = {t.name.lower() for t in data.topics}
    data.topics += [t for t in other.topics if t.name.lower() not in seen_topics]
    seen_kw = {k.lower() for k in data.keywords}
    data.keywords += [k for k in other.keywords if k.lower() not in seen_kw]
    seen_refs = {r.model_dump_json() for r in data.references}
    data.references += [r for r in other.references if r.model_dump_json() not in seen_refs]
    return data


def dedupe_batch(
    records: Sequence[PaperRecord], resolver: PaperResolver | None = None
) -> list[PaperRecord]:
    """Collapse duplicates *within* one batch using the same rules as graph resolution."""
    resolver = resolver or PaperResolver()
    kept: list[PaperRecord] = []
    for record in records:
        pseudo = [_as_candidate(str(i), r) for i, r in enumerate(kept)]
        match = resolver.resolve(record, pseudo)
        if match.paper_id is None:
            kept.append(record)
        else:
            index = int(match.paper_id)
            kept[index] = merge_records(kept[index], record)
    return kept


def _as_candidate(candidate_id: str, record: PaperRecord) -> PaperCandidate:
    return PaperCandidate(
        id=candidate_id,
        doi=record.ids.doi,
        openalex_id=record.ids.openalex,
        arxiv_id=record.ids.arxiv,
        s2_id=record.ids.s2,
        seed_key=record.ids.seed,
        title_key=normalize_title(record.title),
        year=record.year,
        author_keys=record_author_keys(record),
    )


# --------------------------------------------------------------------------- authors
@dataclass(frozen=True)
class AuthorCandidate:
    id: str
    name_key: str
    orcid: str | None = None
    openalex_id: str | None = None
    coauthor_keys: frozenset[str] = frozenset()


def author_node_id_for_key(key: str) -> str:
    return f"author:{key}"


def resolve_author(
    author: AuthorRecord,
    coauthor_names: Iterable[str],
    candidates: Sequence[AuthorCandidate],
) -> tuple[str | None, str]:
    """Return ``(existing_author_id | None, reason)``."""
    if author.key:
        wanted = author_node_id_for_key(author.key)
        if any(c.id == wanted for c in candidates):
            return wanted, "key"
    if author.orcid:
        for c in candidates:
            if c.orcid == author.orcid:
                return c.id, "orcid"
    if author.openalex:
        for c in candidates:
            if c.openalex_id == author.openalex:
                return c.id, "openalex"

    name_key = normalize_name(author.name)
    coauthors = {normalize_name(n) for n in coauthor_names} - {name_key}
    best: tuple[int, str] | None = None
    for c in candidates:
        if c.name_key != name_key:
            continue
        # Distinct identifiers of the same type mean distinct people.
        if author.orcid and c.orcid and author.orcid != c.orcid:
            continue
        if author.openalex and c.openalex_id and author.openalex != c.openalex_id:
            continue
        shared = len(coauthors & c.coauthor_keys)
        if shared and (best is None or shared > best[0] or (shared == best[0] and c.id < best[1])):
            best = (shared, c.id)
    if best:
        return best[1], "name+coauthor"
    return None, "new"


def topic_key(topic: TopicRecord) -> str:
    return normalize_name(topic.name)
