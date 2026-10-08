# Graph schema

The research knowledge graph lives in Neo4j. Constraints and indexes are defined in
[`backend/app/graph/schema.py`](../backend/app/graph/schema.py) and applied with
`researchgraph init`.

## Nodes

| Label | Key properties | Notes |
| --- | --- | --- |
| `Paper` | `id`, `title`, `title_key`, `abstract`, `description`, `year`, `publication_date`, `doi`, `openalex_id`, `arxiv_id`, `s2_id`, `seed_key`, `url`, `language`, `citation_count`, `authors_complete`, `is_stub`, `sources`, `created_at`, `updated_at` | `description` is a curated summary (seed data), never presented as the abstract. `citation_count` is only set when a source reports it. `is_stub = true` marks a referenced paper whose metadata has not been ingested yet. |
| `Author` | `id`, `name`, `name_key`, `orcid`, `openalex_id` | |
| `Institution` | `id`, `name`, `country`, `ror` | |
| `Venue` | `id`, `name`, `type` | `type` ∈ journal, conference, repository, book, other |
| `Topic` | `id`, `name`, `description` | |
| `Keyword` | `id`, `name` | |
| `Community` | `id`, `algorithm`, `size`, `computed_at` | Written by community detection (Phase 4). |

Graph-analytics results are stored as properties on the analysed nodes: `pagerank`,
`betweenness`, `in_degree`, `out_degree`, `community_id`, `analytics_computed_at`.

### Identifiers

`id` is an internal, stable identifier assigned by ResearchGraph (`paper:<uuid>`,
`author:<uuid>`, or a deterministic slug such as `topic:graph-neural-networks` for
vocabulary nodes). External identifiers are separate properties. This keeps identity
stable when the same paper is later seen through a different source.

## Relationships

| Pattern | Properties |
| --- | --- |
| `(:Paper)-[:CITES]->(:Paper)` | `source`, `confidence`, `created_at` |
| `(:Author)-[:WROTE]->(:Paper)` | `position` (1-based author order), `source` |
| `(:Author)-[:AFFILIATED_WITH]->(:Institution)` | `source` |
| `(:Paper)-[:PUBLISHED_IN]->(:Venue)` | `source` |
| `(:Paper)-[:HAS_TOPIC]->(:Topic)` | `score`, `source` |
| `(:Paper)-[:HAS_KEYWORD]->(:Keyword)` | `source` |
| `(:Author)-[:COLLABORATED_WITH]->(:Author)` | `weight` (number of co-authored papers) — derived |
| `(:Topic)-[:RELATED_TO]->(:Topic)` | `weight` (number of papers sharing both topics) — derived |
| `(:Paper)-[:IN_COMMUNITY]->(:Community)` | — written by community detection |

`COLLABORATED_WITH` and `RELATED_TO` are *derived* edges, rebuilt from `WROTE` /
`HAS_TOPIC` by `researchgraph analyze`, so they never drift from the base data.

`HAS_EMBEDDING` from the product spec is modelled as a vector property on `Paper` plus a
Neo4j vector index (`paper_embedding`, cosine; see [ADR-006](adr/006-embeddings-and-vector-store.md)), which lets similarity search and traversal run in the same
Cypher query.

## Constraints

Uniqueness on every `id`, and on `Paper.doi`, `Paper.openalex_id`, `Paper.arxiv_id`,
`Paper.s2_id`, `Paper.seed_key`, `Author.orcid`, `Author.openalex_id`. These back up application-level
entity resolution: even a resolver bug cannot create two papers with the same DOI.

## Indexes

Range indexes on `Paper.year`, `Paper.title_key`, `Paper.is_stub`, `Paper.pagerank`,
`Paper.community_id`, `Author.name_key`, `Topic.name`; full-text indexes `paper_text`
(title, abstract, description), `author_name` and `topic_text`.
