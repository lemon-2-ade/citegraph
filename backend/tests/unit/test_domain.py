import pytest
from pydantic import ValidationError

from app.models.domain import AuthorRecord, ExternalIds, PaperRecord


def test_external_ids_are_normalised() -> None:
    ids = ExternalIds(doi="https://doi.org/10.1000/ABC", arxiv="arXiv:1706.03762v5")
    assert ids.doi == "10.1000/abc"
    assert ids.arxiv == "1706.03762"
    assert not ids.is_empty()
    assert ExternalIds().is_empty()


def test_invalid_doi_is_dropped_not_stored() -> None:
    assert ExternalIds(doi="n/a").doi is None


def test_paper_record_validation() -> None:
    paper = PaperRecord(source="test", ids=ExternalIds(), title="  A &amp; B  ", year=2020)
    assert paper.title == "A & B"
    assert paper.citation_count is None  # never defaulted to a made-up number
    with pytest.raises(ValidationError):
        PaperRecord(source="test", ids=ExternalIds(), title="x", citation_count=-1)
    with pytest.raises(ValidationError):
        PaperRecord(source="test", ids=ExternalIds(), title="x", year=99999)


def test_author_orcid_normalised() -> None:
    author = AuthorRecord(name="Ada Lovelace", orcid="https://orcid.org/0000-0002-1825-0097")
    assert author.orcid == "0000-0002-1825-0097"
