import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.ingestion.seed import DEFAULT_SEED_PATH, SeedDataset, load_dataset, seed_graph, to_records
from tests.fakes import ScriptedGraph


def test_seed_file_is_valid_and_self_consistent() -> None:
    dataset = load_dataset()
    assert dataset.papers, "seed dataset should not be empty"
    records = to_records(dataset)
    assert len(records) == len(dataset.papers)
    for record in records:
        assert record.citation_count is None  # never shipped in the seed
        assert record.abstract is None  # descriptions are not abstracts
        assert record.description
        assert record.ids.seed


def test_seed_references_carry_seed_and_arxiv_ids() -> None:
    records = {r.ids.seed: r for r in to_records(load_dataset())}
    transformer = records["transformer"]
    refs = {r.seed: r for r in transformer.references}
    assert refs["seq2seq"].arxiv == "1409.3215"
    assert refs["lstm"].arxiv is None  # no arXiv version; resolved by seed key


def test_disambiguated_author_keys() -> None:
    records = to_records(load_dataset())
    keys = {a.key for r in records for a in r.authors if a.name == "Meng Wang"}
    assert keys == {"meng-wang", "meng-wang-2"}


def _mutated(**changes: object) -> dict:  # type: ignore[type-arg]
    data = json.loads(Path(DEFAULT_SEED_PATH).read_text())
    data["papers"][0].update(changes)
    return data


def test_dataset_rejects_dangling_citation() -> None:
    with pytest.raises(ValidationError, match="cites unknown paper"):
        SeedDataset.model_validate(_mutated(cites=["does-not-exist"]))


def test_dataset_rejects_citation_to_future_paper() -> None:
    data = json.loads(Path(DEFAULT_SEED_PATH).read_text())
    newest = max(data["papers"], key=lambda p: p["year"])["key"]
    data["papers"][0]["cites"] = [newest]
    data["papers"][0]["year"] = 1990
    with pytest.raises(ValidationError, match="cites later paper"):
        SeedDataset.model_validate(data)


async def test_seed_load_links_all_citations_without_stubs() -> None:
    # One batch: the fake graph cannot return nodes written by earlier batches.
    graph = ScriptedGraph()
    stats = await seed_graph(graph, batch_size=1000)  # type: ignore[arg-type]
    dataset = load_dataset()
    unique_authors = {a.key for r in to_records(dataset) for a in r.authors}
    assert stats.authors_created == len(unique_authors)
    assert stats.papers_created == len(dataset.papers)
    assert stats.stubs_created == 0
    assert stats.citations == sum(len(p.cites) for p in dataset.papers)
