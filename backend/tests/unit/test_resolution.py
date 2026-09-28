from app.ingestion.resolution import (
    AuthorCandidate,
    PaperCandidate,
    PaperResolver,
    author_overlap,
    dedupe_batch,
    merge_records,
    resolve_author,
)
from app.models.domain import AuthorRecord, ExternalIds, PaperRecord, TopicRecord


def paper(
    title: str,
    *,
    year: int | None = 2017,
    authors: tuple[str, ...] = ("Ashish Vaswani", "Noam Shazeer"),
    **ids: str,
) -> PaperRecord:
    return PaperRecord(
        source="test",
        ids=ExternalIds(**ids),
        title=title,
        year=year,
        authors=[AuthorRecord(name=a) for a in authors],
    )


def cand(cid: str, title: str | None = None, **kw) -> PaperCandidate:  # type: ignore[no-untyped-def]
    from app.ingestion.normalize import normalize_title

    return PaperCandidate(id=cid, title_key=normalize_title(title) if title else None, **kw)


resolver = PaperResolver()


# -- identifier matching -------------------------------------------------------------
def test_doi_match_wins() -> None:
    match = resolver.resolve(
        paper("Totally different title", doi="10.1000/abc"), [cand("p1", doi="10.1000/abc")]
    )
    assert match.paper_id == "p1"
    assert match.reason == "doi"


def test_arxiv_match_with_version_suffix_normalised() -> None:
    match = resolver.resolve(paper("X", arxiv="1706.03762v5"), [cand("p1", arxiv_id="1706.03762")])
    assert match.paper_id == "p1"


def test_identifiers_pointing_to_two_nodes_schedule_a_merge() -> None:
    # A seed node known by arXiv id, and a stub created from a reference by OpenAlex id.
    record = paper("Attention Is All You Need", arxiv="1706.03762", openalex="W1")
    candidates = [
        cand("stub", openalex_id="W1", is_stub=True),
        cand("seed", "Attention Is All You Need", arxiv_id="1706.03762"),
    ]
    match = resolver.resolve(record, candidates)
    assert match.paper_id == "seed"  # real node preferred over stub
    assert match.merge_ids == ["stub"]


def test_conflicting_nodes_are_reported_not_merged() -> None:
    record = paper("X", doi="10.1000/a", openalex="W1")
    candidates = [
        cand("a", doi="10.1000/a", openalex_id="W9"),
        cand("b", openalex_id="W1", doi="10.1000/b"),
    ]
    match = resolver.resolve(record, candidates)
    assert match.paper_id == "a"
    assert match.merge_ids == []
    assert match.conflicts and "b" in match.conflicts[0]


# -- fuzzy matching -------------------------------------------------------------------
def test_title_case_and_punctuation_variants_match_with_author_overlap() -> None:
    match = resolver.resolve(
        paper("Attention is all you need.", authors=("A. Vaswani", "N. Shazeer", "N. Parmar")),
        [cand("p1", "Attention Is All You Need", year=2017, author_keys=frozenset({"a vaswani"}))],
    )
    assert match.paper_id == "p1"
    assert match.reason == "title+year+authors"


def test_same_title_different_authors_is_not_merged() -> None:
    match = resolver.resolve(
        paper("Introduction", authors=("Jane Doe",)),
        [cand("p1", "Introduction", year=2017, author_keys=frozenset({"j smith"}))],
    )
    assert match.is_new


def test_same_title_far_apart_years_is_not_merged() -> None:
    match = resolver.resolve(
        paper("Deep Learning", year=2015),
        [cand("p1", "Deep Learning", year=2005, author_keys=frozenset({"a vaswani"}))],
    )
    assert match.is_new


def test_preprint_one_year_earlier_still_matches() -> None:
    match = resolver.resolve(
        paper("Graph Attention Networks", year=2017, authors=("Petar Velickovic",)),
        [
            cand(
                "p1", "Graph Attention Networks", year=2018, author_keys=frozenset({"p velickovic"})
            )
        ],
    )
    assert match.paper_id == "p1"


def test_without_authors_requires_exact_title_and_years() -> None:
    record = paper("Graph Attention Networks", authors=())
    assert (
        resolver.resolve(record, [cand("p1", "Graph Attention Networks", year=2017)]).paper_id
        == "p1"
    )
    assert resolver.resolve(record, [cand("p1", "Graph Attention Networks")]).is_new
    assert resolver.resolve(record, [cand("p1", "Graph Attention Network", year=2017)]).is_new


def test_conflicting_identifier_blocks_fuzzy_match() -> None:
    match = resolver.resolve(
        paper("Attention Is All You Need", openalex="W1"),
        [
            cand(
                "p1",
                "Attention Is All You Need",
                openalex_id="W2",
                year=2017,
                author_keys=frozenset({"a vaswani"}),
            )
        ],
    )
    assert match.is_new


def test_stubs_are_never_fuzzy_matched() -> None:
    match = resolver.resolve(paper("X"), [cand("s", "X", is_stub=True, year=2017)])
    assert match.is_new


def test_author_overlap() -> None:
    assert author_overlap({"a b", "c d"}, {"a b"}) == 1.0
    assert author_overlap(set(), {"a b"}) is None


# -- batches ----------------------------------------------------------------------------
def test_dedupe_batch_merges_duplicates_and_fills_gaps() -> None:
    first = paper("Attention Is All You Need", arxiv="1706.03762")
    second = paper("Attention is all you need", doi="10.5555/3295222.3295349")
    second.topics = [TopicRecord(name="Transformers")]
    second.citation_count = 5
    other = paper("BERT", authors=("Jacob Devlin",), year=2019)
    result = dedupe_batch([first, second, other])
    assert len(result) == 2
    merged = result[0]
    assert merged.ids.arxiv == "1706.03762"
    assert merged.ids.doi == "10.5555/3295222.3295349"
    assert [t.name for t in merged.topics] == ["Transformers"]
    assert merged.citation_count == 5


def test_merge_records_keeps_primary_values() -> None:
    a = paper("T", doi="10.1000/a")
    a.abstract = "primary"
    b = paper("T", doi="10.1000/b")
    b.abstract = "secondary"
    merged = merge_records(a, b)
    assert merged.abstract == "primary"
    assert merged.ids.doi == "10.1000/a"


# -- authors ------------------------------------------------------------------------------
def test_author_resolution_by_identifiers() -> None:
    candidates = [AuthorCandidate(id="a1", name_key="x", orcid="0000-0002-1825-0097")]
    author = AuthorRecord(name="Someone", orcid="0000-0002-1825-0097")
    assert resolve_author(author, [], candidates) == ("a1", "orcid")


def test_author_resolution_by_curated_key() -> None:
    candidates = [AuthorCandidate(id="author:yoshua-bengio", name_key="yoshua bengio")]
    author = AuthorRecord(name="Yoshua Bengio", key="yoshua-bengio")
    assert resolve_author(author, [], candidates) == ("author:yoshua-bengio", "key")


def test_same_name_requires_shared_coauthor() -> None:
    candidates = [
        AuthorCandidate(id="a1", name_key="wei wang", coauthor_keys=frozenset({"li zhang"})),
        AuthorCandidate(id="a2", name_key="wei wang", coauthor_keys=frozenset({"maria garcia"})),
    ]
    author = AuthorRecord(name="Wei Wang")
    assert resolve_author(author, ["Wei Wang", "Maria Garcia"], candidates) == (
        "a2",
        "name+coauthor",
    )
    assert resolve_author(author, ["Someone Else"], candidates) == (None, "new")


def test_same_name_with_different_orcid_is_different_person() -> None:
    candidates = [
        AuthorCandidate(
            id="a1",
            name_key="wei wang",
            orcid="0000-0001-0000-0001",
            coauthor_keys=frozenset({"li zhang"}),
        )
    ]
    author = AuthorRecord(name="Wei Wang", orcid="0000-0002-0000-0002")
    assert resolve_author(author, ["Li Zhang"], candidates) == (None, "new")
