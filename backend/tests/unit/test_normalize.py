import pytest

from app.ingestion.normalize import (
    author_key,
    clean_text,
    normalize_arxiv_id,
    normalize_doi,
    normalize_name,
    normalize_orcid,
    normalize_title,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10.18653/v1/N19-1423", "10.18653/v1/n19-1423"),
        ("https://doi.org/10.1145/3292500.3330919", "10.1145/3292500.3330919"),
        ("http://dx.doi.org/10.1000/XYZ", "10.1000/xyz"),
        ("doi: 10.1000/abc", "10.1000/abc"),
        ("not-a-doi", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_doi(raw: str | None, expected: str | None) -> None:
    assert normalize_doi(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1706.03762", "1706.03762"),
        ("1706.03762v7", "1706.03762"),
        ("arXiv:1810.04805v2", "1810.04805"),
        ("https://arxiv.org/abs/2005.11401", "2005.11401"),
        ("https://arxiv.org/pdf/2005.11401v4", "2005.11401"),
        ("hep-th/9901001v1", "hep-th/9901001"),
        ("garbage", None),
    ],
)
def test_normalize_arxiv(raw: str, expected: str | None) -> None:
    assert normalize_arxiv_id(raw) == expected


def test_normalize_orcid() -> None:
    assert normalize_orcid("https://orcid.org/0000-0002-1825-009x") == "0000-0002-1825-009X"
    assert normalize_orcid("nope") is None


def test_title_normalisation_is_case_and_punctuation_insensitive() -> None:
    assert normalize_title("Attention Is All You Need") == normalize_title(
        "Attention is all you need."
    )
    assert normalize_title("BERT: Pre-training of Deep") == "bert pre training of deep"


def test_title_normalisation_handles_accents_and_markup() -> None:
    assert normalize_title("Réseaux <i>de</i> neurones") == "reseaux de neurones"


def test_clean_text_unescapes_and_collapses_whitespace() -> None:
    assert clean_text("  A &amp; B\n\n<jats:p>C</jats:p> ") == "A & B C"


def test_author_key_matches_initial_forms() -> None:
    assert author_key("Ashish Vaswani") == author_key("A. Vaswani") == "a vaswani"
    assert author_key("Jürgen Schmidhuber") == "j schmidhuber"
    assert normalize_name("Jean-Pierre O'Neil") == "jean pierre o neil"
