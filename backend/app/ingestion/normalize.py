"""Pure normalisation helpers for identifiers, titles and names.

These functions are deliberately small and side-effect free; entity resolution depends
on them producing identical keys for equivalent inputs.
"""

from __future__ import annotations

import html
import re
import unicodedata

_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
_DOI_SHAPE = re.compile(r"^10\.\d{4,9}/\S+$")
_ARXIV_NEW = re.compile(r"(\d{4}\.\d{4,5})(?:v\d+)?$")
_ARXIV_OLD = re.compile(r"([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?$", re.IGNORECASE)
_ORCID = re.compile(r"(\d{4}-\d{4}-\d{4}-\d{3}[\dX])$", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")


def clean_text(value: str) -> str:
    """Unescape HTML entities, strip markup/JATS tags and collapse whitespace."""
    value = html.unescape(value)
    value = _TAGS.sub(" ", value)
    return _WS.sub(" ", value).strip()


def normalize_doi(value: str | None) -> str | None:
    """Return a lower-cased bare DOI (``10.xxxx/...``) or ``None`` if invalid."""
    if not value:
        return None
    doi = _DOI_PREFIX.sub("", value.strip()).strip().lower()
    return doi if _DOI_SHAPE.match(doi) else None


def normalize_arxiv_id(value: str | None) -> str | None:
    """Return an arXiv identifier without URL prefix or version suffix."""
    if not value:
        return None
    value = value.strip().removeprefix("arXiv:").removeprefix("arxiv:")
    value = value.rstrip("/")
    for pattern in (_ARXIV_NEW, _ARXIV_OLD):
        match = pattern.search(value)
        if match:
            return match.group(1).lower() if pattern is _ARXIV_OLD else match.group(1)
    return None


def normalize_orcid(value: str | None) -> str | None:
    if not value:
        return None
    match = _ORCID.search(value.strip())
    return match.group(1).upper() if match else None


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_title(title: str) -> str:
    """Case-, accent- and punctuation-insensitive title key.

    ``"Attention Is All You Need"`` and ``"Attention is all you need."`` map to the same
    key. Used as a *candidate* key only; resolution also checks year and authors.
    """
    text = strip_accents(clean_text(title)).lower()
    text = _NON_ALNUM.sub(" ", text)
    return _WS.sub(" ", text).strip()


def normalize_name(name: str) -> str:
    """Lower-case, accent-free person/organisation name with punctuation removed."""
    text = strip_accents(clean_text(name)).lower().replace("-", " ")
    text = _NON_ALNUM.sub(" ", text)
    return _WS.sub(" ", text).strip()


def author_key(name: str) -> str:
    """Coarse author key: surname plus first initial (``"a vaswani"``).

    Different sources render names differently ("Ashish Vaswani", "A. Vaswani"). The key
    is used to measure author-list overlap between paper candidates, not to merge
    authors on its own.
    """
    parts = normalize_name(name).split()
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0][0]} {parts[-1]}"


def slugify(value: str) -> str:
    return normalize_name(value).replace(" ", "-")
