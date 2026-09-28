# Seed dataset

`papers.json` is a small, **hand-curated** sample of well-known papers used to run and
demonstrate ResearchGraph without network access. `researchgraph seed` loads it.

It spans transformers and large language models, retrieval-augmented generation,
knowledge graphs, graph neural networks, network embedding, temporal graphs and
graph-based fraud detection, so the demo scenarios in the README (e.g. "graph neural
networks for fraud detection") have connected material to work with.

## What it contains

| Field | Notes |
| --- | --- |
| `title`, `year`, `arxiv`, `venue` | Entered by hand. `year` is the year of first public release (arXiv or venue, whichever came first). |
| `authors` | Full author lists except where `authors_complete` is `false` (deliberately truncated). The same name across papers is asserted to be the same person; `{name, key}` objects disambiguate different people who share a name. |
| `topics`, `keywords` | Curated labels from a small topic vocabulary defined in the file. |
| `description` | A one-sentence summary written for this dataset. **Not** the paper's abstract. |
| `cites` | A curated, high-confidence **subset** of each paper's references *among papers in this file*. Not a complete reference list. |

## What it deliberately does not contain

- **No citation counts** and **no abstracts** — these must come from a real source.
- **No DOIs** — only arXiv IDs, which are easy to verify.

The file's `provenance` block states the same. The loader validates referential
integrity (no dangling or future citations, known venues/topics) on every load.

## Growing it with real data

Run an OpenAlex ingestion job (see `docs/ingestion.md`). Entity resolution merges OpenAlex
records into seed papers by arXiv ID, or by title + year + author overlap, adding DOIs,
abstracts, full author lists, source-reported citation counts and the complete reference
lists.
