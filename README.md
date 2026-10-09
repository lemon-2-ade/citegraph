# ResearchGraph — AI-Powered Research Intelligence & Citation Knowledge Graph

> Use a citation knowledge graph as structured research memory, and AI as the reasoning
> and interaction layer over that graph.

ResearchGraph ingests scholarly metadata, resolves duplicate papers and authors, and
builds a Neo4j knowledge graph of papers, authors, institutions, venues, topics and
citations. Graph analytics — PageRank, centrality, community detection, similarity,
shortest paths — run on that graph. Later phases add embeddings, semantic search,
graph-aware RAG, natural-language graph querying, recommendations and a web client.

**Status:** Phases 1–5 (foundation, graph model, ingestion, analytics, frontend foundation)
are implemented. The AI layer and the graph visualisation are not built yet — see the
[roadmap](#roadmap).

## Contents

- [Problem](#problem) · [What exists today](#what-exists-today) · [Architecture](#architecture)
- [Graph schema](#graph-schema) · [Data pipeline](#data-pipeline) · [Analytics](#analytics)
- [API](#api) · [Quick start](#quick-start) · [CLI](#cli) · [Dataset](#dataset)
- [Testing](#testing) · [Engineering decisions](#engineering-decisions)
- [Limitations](#limitations) · [Roadmap](#roadmap)

## Problem

Keyword search does not answer the questions researchers actually have: which papers are
foundational to a topic, how an idea evolved, which works bridge two areas, who works on
closely related problems, or why a paper matters. Those questions are about
*relationships* — citations, co-authorship, shared topics — which is what a citation
knowledge graph stores explicitly.

## What exists today

| Area | Implemented |
| --- | --- |
| Graph model | Neo4j schema with uniqueness constraints on internal and external IDs (DOI, OpenAlex, arXiv, S2, ORCID), range and full-text indexes |
| Ingestion | `PaperSource` abstraction, OpenAlex provider (cursor paging, rate limiting, retries with `Retry-After`), raw payload storage, validation/normalisation, in-batch dedup, entity resolution, idempotent graph loading, stub papers for unresolved references, reference hydration |
| Reliability | Jobs and checkpoints in PostgreSQL; a failed job resumes from its last committed page; background worker (Arq) |
| Analytics | PageRank, degree, betweenness (sampled on large graphs), Louvain/Leiden communities, weighted collaboration graph, topic co-occurrence, bibliographic coupling, co-citation, Personalized PageRank, shortest paths — on Neo4j GDS or NetworkX |
| API | Papers, citations/references, authors, topics, communities, influence rankings, similarity, shortest paths, ingestion jobs, analytics runs; OpenAPI at `/api/docs` |
| Web client | Vite + React + TypeScript app: dashboard, paper browser with filters, paper detail with citations and similar papers; types generated from the OpenAPI schema ([docs/frontend.md](docs/frontend.md)) |
| Engineering | Docker Compose stack, structured JSON logs with request/job IDs, admin-token-protected write endpoints, `mypy --strict`, ruff, unit + integration tests, Cypher linting, CI workflow |

## Architecture

```text
 Web client (React SPA, nginx)
        │  REST
 FastAPI ── read ──► Neo4j 5 + GDS        (knowledge graph + analytics properties)
        │
        └─ enqueue ─► Redis ─► Arq worker ─► ingestion pipeline ─► Neo4j
                                        └──► analytics service  ─► Neo4j
                          jobs, checkpoints, raw payloads, runs ─► PostgreSQL
```

Details: [docs/architecture.md](docs/architecture.md). Decisions:
[docs/adr/](docs/adr/README.md).

## Graph schema

```text
(:Author)-[:WROTE {position}]->(:Paper)-[:CITES]->(:Paper)
(:Author)-[:AFFILIATED_WITH]->(:Institution)
(:Paper)-[:PUBLISHED_IN]->(:Venue)
(:Paper)-[:HAS_TOPIC {score}]->(:Topic)-[:RELATED_TO {weight}]->(:Topic)
(:Paper)-[:HAS_KEYWORD]->(:Keyword)
(:Author)-[:COLLABORATED_WITH {weight}]->(:Author)
(:Paper|Author)-[:IN_COMMUNITY]->(:Community)
```

Full property lists, identifiers and constraints: [docs/graph-schema.md](docs/graph-schema.md).

## Data pipeline

```text
OpenAlex → raw payload (PostgreSQL) → parse/validate/normalise → in-batch dedup
        → entity resolution against Neo4j → idempotent MERGE → checkpoint
```

Entity resolution is conservative: shared persistent identifiers match (and nodes that
turn out to be the same work are merged); otherwise a match needs title similarity,
compatible years, no conflicting identifiers and author overlap. See
[docs/ingestion.md](docs/ingestion.md).

## Analytics

`researchgraph analyze` computes PageRank, degree and betweenness for the citation and
collaboration graphs, detects communities (Louvain or Leiden) and summarises each
community's dominant topics. It uses Neo4j GDS when installed and NetworkX otherwise.

PageRank here measures **structural influence within the ingested graph**, not research
quality; API responses say so explicitly.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/papers` | List papers (filters: year range, topic; sort: year, pagerank, cited_by) |
| GET | `/api/papers/{id}` | Paper details, authors, venue, topics, graph metrics |
| GET | `/api/papers/{id}/citations` · `/references` | Citing / cited papers |
| GET | `/api/papers/{id}/similar` | Bibliographic coupling or co-citation, with explanations |
| GET | `/api/papers/{id}/related` | Personalized PageRank over the local neighbourhood |
| GET | `/api/authors/{id}` | Papers, collaborators, topics, institutions, metrics |
| GET | `/api/topics` · `/api/topics/{id}` | Topics, related topics, top papers/authors, papers per year |
| GET | `/api/communities` · `/api/communities/{id}` | Research communities and their profile |
| GET | `/api/analytics/summary` · `/api/analytics/influential` · `/api/analytics/years` | Graph counts, influence rankings, papers per year |
| GET | `/api/search/papers?q=&mode=keyword\|semantic\|hybrid` · `/api/papers/{id}/semantic-similar` | Paper search by BM25, embeddings or rank-fused hybrid; neighbours by meaning |
| GET · POST | `/api/papers/{id}/insight` | Stored AI summary and structured extraction; POST generates it with the configured LLM (admin-gated) |
| GET | `/api/search?q=` | Keyword search (Lucene full-text, prefix on the last term) over papers, authors, topics |
| GET | `/api/graph/overview` · `/api/graph/neighborhood/{id}` | Capped node/edge views for the graph explorer |
| GET | `/api/graph/shortest-path` | Shortest path between two nodes over chosen relationship types |
| POST/GET | `/api/ingestion/jobs[/{id}[/resume]]` | Ingestion jobs (admin) |
| POST/GET | `/api/analytics/runs[/{id}]` | Analytics runs (admin) |
| GET | `/api/health` · `/api/health/ready` | Liveness / readiness (Neo4j + PostgreSQL) |

## Quick start

```bash
cp .env.example .env                 # set passwords and ADMIN_API_TOKEN
docker compose up -d --build
docker compose exec backend researchgraph init
docker compose exec backend researchgraph seed
docker compose exec backend researchgraph analyze
# Web UI: http://localhost:8080   API docs: http://localhost:8000/api/docs
# Neo4j Browser: http://localhost:7474
```

Example requests after seeding and analysing (IDs come from the list endpoints):

```bash
curl 'localhost:8000/api/analytics/influential?entity=paper&metric=pagerank&limit=10'
curl 'localhost:8000/api/communities?scope=papers'
curl 'localhost:8000/api/papers?sort=pagerank&year_from=2018'
curl 'localhost:8000/api/graph/shortest-path?source=<paper-id>&target=<paper-id>&relationships=CITES'
```

More: [docs/development.md](docs/development.md).

## CLI

```text
researchgraph init                      constraints, indexes, tables
researchgraph seed                      load the curated seed dataset
researchgraph ingest --query "..."      ingest from OpenAlex (--enqueue, --resume <job-id>, --hydrate N)
researchgraph jobs                      recent ingestion jobs
researchgraph analyze                   PageRank, centrality, communities (--backend, --algorithm)
researchgraph embed                     embed papers + build the vector index (--rebuild after changing model)
researchgraph insights                  generate AI summaries/extractions for papers (--limit, --force)
```

## Dataset

The repository ships a small, **hand-curated** seed dataset (`data/seed/papers.json`) so
the application works without network access: well-known papers across transformers and
LLMs, retrieval-augmented generation, knowledge graphs, graph neural networks and
graph-based fraud detection, with curated citation edges among them. It deliberately
contains no citation counts, abstracts or DOIs; see
[data/seed/README.md](data/seed/README.md) for exactly what it contains and how it was
made. OpenAlex ingestion adds authoritative metadata and merges into the seed records.

## Testing

```bash
make test          # unit tests
make lint          # ruff + mypy --strict
make lint-cypher   # every Cypher query parsed and semantically checked
make test-integration   # needs Neo4j/PostgreSQL; see docs/development.md
make frontend-check     # frontend typecheck, eslint, vitest
```

Integration tests (Neo4j client, schema, loader, seed, NetworkX/GDS analytics,
PostgreSQL repositories) are skipped unless test databases are configured; the CI
workflow runs them against service containers.

## Engineering decisions

- [ADR-001](docs/adr/001-neo4j.md) Neo4j for the knowledge graph
- [ADR-002](docs/adr/002-postgresql.md) PostgreSQL for operational data
- [ADR-004](docs/adr/004-fastapi.md) FastAPI
- [ADR-005](docs/adr/005-background-workers.md) Arq workers with durable state in PostgreSQL

ADR-003 (hybrid graph + vector retrieval) and ADR-007 (LLM
provider abstraction) will be written with those phases.

## Limitations

- No evaluation results exist yet. Retrieval, recommendation and RAG metrics will be
  reported only once measured (Phase 14).
- The seed dataset is small and hand-curated; its citation edges are a subset of each
  paper's references.
- Venue names from different sources are not unified; fuzzy title matching only
  considers exact normalised-title candidates.
- Betweenness on large graphs is a sampled estimate, and absolute values differ between
  the GDS and NetworkX backends (rankings are what the application uses).
- PostgreSQL schema changes are applied with `create_all`; migrations (Alembic) are not
  set up yet.
- No end-user authentication or rate limiting yet; write operations are admin-only.
- The frontend has component tests against a mocked API but no browser (end-to-end) tests
  or accessibility audit yet; the nginx image and Compose wiring are exercised only by running
  the stack.

## Roadmap

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Repository, Docker, configuration, tooling | done |
| 2 | Neo4j integration, schema, repositories | done |
| 3 | Ingestion pipeline (OpenAlex, dedup, resumable jobs, seed data) | done |
| 4 | Graph analytics (PageRank, centrality, communities, similarity, paths) | done |
| 5 | Frontend foundation: app shell, typed API client, dashboard, paper browser and detail | done |
| 6 | Research explorer: authors, topics, communities, interactive graph explorer, keyword search | done |
| 7 | Embeddings, Neo4j vector index, semantic and hybrid search | done |
| 8 | LLM provider abstraction, AI paper summaries and structured extraction | done |
| 9 | Graph-aware RAG with citations | planned |
| 10 | Natural language → validated read-only Cypher | planned |
| 11–13 | Recommendations, research trends, reading paths | planned |
| 14–17 | Evaluation, security hardening, testing/performance, polish | planned |
