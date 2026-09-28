# ResearchGraph — AI-Powered Research Intelligence & Citation Knowledge Graph

> Use a citation knowledge graph as structured research memory, and AI as the
> reasoning and interaction layer over that graph.

ResearchGraph ingests scholarly metadata (OpenAlex first, other providers via a
common interface), resolves duplicates, and builds a Neo4j knowledge graph of
papers, authors, institutions, venues, topics and citations. Graph analytics
(PageRank, centrality, community detection, similarity, shortest paths) run on
top of that graph. Later phases add embeddings, semantic search, graph-aware RAG,
natural-language graph querying and recommendations.

**Status:** early development. See [Roadmap](#roadmap) for what exists today.

## Repository layout

```text
backend/        FastAPI service, ingestion pipeline, graph + analytics code, tests
frontend/       React + TypeScript web client (Phase 5+)
data/           Seed dataset
scripts/        Database initialisation and helper scripts
evaluation/     Evaluation datasets and harness (Phase 14)
docs/           Architecture docs and ADRs
infrastructure/ Container configuration
```

## Roadmap

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Repository setup, Docker, configuration, tooling | in progress |
| 2 | Neo4j integration, schema, repositories | planned |
| 3 | Ingestion pipeline (OpenAlex, dedup, resumable jobs) | planned |
| 4 | Graph analytics | planned |
| 5–17 | Frontend, embeddings, AI, RAG, NL→Cypher, recommendations, trends, evaluation, hardening | planned |
