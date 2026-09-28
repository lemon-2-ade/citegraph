# Ingestion

Ingestion turns external scholarly metadata into the research knowledge graph.

```text
PaperSource.search / fetch_papers        (OpenAlex; rate limited, retried)
      │ raw JSON
      ▼
raw_records (PostgreSQL)                 kept for reprocessing without re-fetching
      │
      ▼
PaperSource.parse → PaperRecord          validation + normalisation (DOI, arXiv, ORCID,
      │                                  HTML entities, abstract reconstruction)
      ▼
dedupe_batch                             duplicates inside one page
      │
      ▼
PaperResolver / resolve_author           entity resolution against Neo4j
      │
      ▼
GraphLoader                              idempotent MERGE of papers, authors, venues,
      │                                  topics, keywords, affiliations, stubs, CITES
      ▼
checkpoint (PostgreSQL)                  cursor + counters, committed after every page
```

Code: `backend/app/ingestion/` (pipeline, loader, resolution, normalisation, sources) and
`backend/app/services/ingestion.py` (source registry, job execution).

## Running ingestion

```bash
# inline, from the backend directory (needs Neo4j + PostgreSQL)
uv run researchgraph ingest --query "graph neural networks fraud detection" \
    --max-results 300 --year-from 2016 --hydrate 100

# hand it to the background worker instead
uv run researchgraph ingest --query "retrieval augmented generation" --enqueue

# via the API (X-Admin-Token required when ADMIN_API_TOKEN is set)
curl -X POST localhost:8000/api/ingestion/jobs -H 'Content-Type: application/json' \
     -H "X-Admin-Token: $ADMIN_API_TOKEN" \
     -d '{"source": "openalex", "params": {"query": "knowledge graph embedding", "max_results": 200}}'
```

Set `OPENALEX_MAILTO` so requests use OpenAlex's "polite pool". The default rate is
5 requests/second (`OPENALEX_REQUESTS_PER_SECOND`).

## Jobs, checkpoints and resuming

A job row in `ingestion_jobs` holds its parameters, status, attempt count, counters and a
checkpoint:

| Stage | Checkpoint | Meaning |
| --- | --- | --- |
| `search` | `{"cursor": ..., "fetched": n}` | next OpenAlex cursor and results processed so far |
| `hydrate` | `{"hydrated": n}` | stub papers already looked up |
| `done` | — | finished |

The checkpoint is committed **after** the page has been written to Neo4j. If the process
dies between the graph write and the checkpoint, the resumed job re-processes that one
page; because every write is a `MERGE` keyed on stable IDs, this is harmless.

Resume a failed or interrupted job with `researchgraph ingest --resume <job-id>` or
`POST /api/ingestion/jobs/{id}/resume`. The worker never retries a job blindly
(`max_tries = 1`): failures are recorded with their error and resumed deliberately.

## Hydration of references

OpenAlex returns each work's `referenced_works`. References that are not yet in the graph
become **stub** papers (`is_stub = true`, identifier only) so the `CITES` edge exists
immediately. With `--hydrate N` the job then fetches full metadata for the N most-cited
stubs (by in-graph citations) in batches of 50, which grows the graph one hop outward
around the most important references. Stubs the source cannot return are marked
`hydration_attempted` so they are not selected forever.

## Entity resolution

See the module docstring of `app/ingestion/resolution.py` for the exact rules. In short:

1. **Identifiers first.** DOI, OpenAlex ID, arXiv ID, Semantic Scholar ID or seed key →
   same work. When identifiers point at *two* existing nodes (e.g. a seed paper known by
   arXiv ID and a stub known by OpenAlex ID) they are **merged**: relationships move to the
   canonical node, properties are coalesced, and the dropped node's ID is recorded in
   `merged_ids`. If the two nodes carry *conflicting* values of the same identifier type
   the merge is refused and logged.
2. **Fuzzy matching** requires all of: title similarity ≥ 0.95 (normalised,
   case/accents/punctuation-insensitive), publication years within ±1 (preprint vs.
   published), no conflicting identifiers, and author-list overlap ≥ 0.5 (overlap
   coefficient on surname + first initial, robust to truncated lists). Without author
   lists, only near-exact titles with both years known match.
3. **Authors** match by ORCID, OpenAlex ID or curated key; a bare name only matches an
   existing author with the same normalised name *who shares a co-author* with the
   incoming paper, or an author already attached to the same paper.

The resolver is deliberately conservative: a wrong merge corrupts the citation graph,
whereas a missed merge only leaves a duplicate that a later run with more identifiers
can merge. Uniqueness constraints on every external identifier back this up in the
database.

Known limitations:

- Fuzzy candidates are retrieved by *exact* normalised-title key, so a title with a typo
  is only matched through identifiers.
- Venues from different sources ("NeurIPS" vs. "Neural Information Processing Systems")
  are not unified yet.

## Adding a source

Implement `PaperSource` (`app/ingestion/sources/base.py`): `search`, `fetch_paper`,
`fetch_papers`, `fetch_citations`, `fetch_authors`, `external_id` and `parse`, set `name`
and `id_field`, and register a factory in `app/services/ingestion.py::SOURCES`. Everything
downstream — raw storage, validation, resolution, loading, checkpoints — is shared.

## Seed dataset

`researchgraph seed` loads `data/seed/papers.json`, a hand-curated sample that makes the
application usable offline. Its contents and limitations are described in
[`data/seed/README.md`](../data/seed/README.md).
