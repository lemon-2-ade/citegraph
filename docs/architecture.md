# Architecture

ResearchGraph uses a citation knowledge graph as structured research memory; AI features
(later phases) act as the reasoning and interaction layer over that graph.

This document describes what exists today (Phases 1–5). Planned components are marked.

```text
                  ┌──────────────────────────────┐
                  │ React SPA behind nginx       │
                  └──────────────┬───────────────┘
                                 │ REST (OpenAPI at /api/docs)
                  ┌──────────────▼───────────────┐
                  │ FastAPI  (app/main.py)       │  request IDs, structured logs,
                  │  api/  papers, entities,     │  security headers, CORS,
                  │        analytics, ingestion  │  admin token for write ops
                  └───┬──────────────┬───────────┘
          read (Cypher)│              │ enqueue job id
                       │        ┌─────▼──────┐
                       │        │   Redis    │  queue only (no durable state)
                       │        └─────┬──────┘
                       │        ┌─────▼──────────────────────┐
                       │        │ Arq worker (workers/tasks) │  ingestion + analytics
                       │        └─────┬──────────────┬───────┘
                ┌──────▼──────────────▼──┐     ┌─────▼────────────────────┐
                │ Neo4j 5 + GDS          │     │ PostgreSQL 16            │
                │ knowledge graph,       │     │ ingestion jobs +         │
                │ analytics properties   │     │ checkpoints, raw payloads│
                └──────────▲─────────────┘     │ analytics runs           │
                           │                   └──────────▲───────────────┘
                ┌──────────┴───────────────────────────────┴──────┐
                │ Ingestion pipeline (app/ingestion)               │
                │ PaperSource → raw → parse → dedupe → resolve →   │
                │ GraphLoader → checkpoint                         │
                └──────────▲───────────────────────────────────────┘
                           │ HTTPS (rate limited, retried)
                     OpenAlex (other providers implement PaperSource)
```

## Backend layout

| Package | Responsibility |
| --- | --- |
| `app/core` | Settings (env vars, `SecretStr` secrets), structured logging, middleware, errors, shared `Resources` |
| `app/graph` | `GraphClient` (managed read/write transactions, timing) and the Neo4j schema |
| `app/db` | SQLAlchemy models and engine/session factory for PostgreSQL |
| `app/models` | Source-independent domain records (`PaperRecord`, …) |
| `app/ingestion` | Sources, normalisation, entity resolution, graph loading, pipeline, seed dataset |
| `app/analytics` | Algorithms, NetworkX/GDS backends, batch analytics service, read-side queries |
| `app/repositories` | Read models over Neo4j (papers, authors, topics) and PostgreSQL (jobs, runs) |
| `app/services` | Orchestration shared by API, worker and CLI |
| `app/api` | HTTP routes and dependencies |
| `app/workers` | Arq task definitions |
| `app/cli.py` | `researchgraph` command |

The web client lives in `frontend/` and is described in [frontend.md](frontend.md).

Planned packages from the product spec (`ai/`, `rag/`) will be added with the phases that
need them rather than as empty placeholders.

## Key design decisions

- **Polyglot persistence** ([ADR-001](adr/001-neo4j.md), [ADR-002](adr/002-postgresql.md)).
  Knowledge lives in Neo4j; operational state (jobs, checkpoints, raw payloads, analytics
  runs) lives in PostgreSQL. Redis is only a queue.
- **Durable jobs, thin queue** ([ADR-005](adr/005-background-workers.md)). Queue messages
  carry an ID; progress is checkpointed in PostgreSQL so work resumes after a crash.
- **Idempotent graph writes.** Every load is a `MERGE` keyed on stable internal IDs, so
  re-processing a batch cannot duplicate data. Uniqueness constraints on external
  identifiers back up the entity resolver.
- **Two analytics backends, one interface.** Neo4j GDS is used when installed; NetworkX
  over a projection otherwise. Both are exercised by tests (NetworkX in unit tests, GDS in
  integration tests against the Compose stack).
- **Read transactions for reads.** Every read runs in a managed read transaction; queries
  built at runtime (shortest paths today, NL→Cypher later) use only whitelisted parts and
  still execute read-only, so Neo4j itself rejects writes.
- **No invented numbers.** Citation counts are stored only when a source reports them;
  the API distinguishes `citation_count` (source-reported) from `cited_by_in_graph`
  (edges present in this graph). Analytics responses carry notes on what the metric does
  and does not mean.

## Analytics

`researchgraph analyze` (or `POST /api/analytics/runs`) runs:

1. derived edges: `COLLABORATED_WITH` (weight = shared papers), `RELATED_TO` (weight = papers
   sharing both topics);
2. citation graph: in/out degree, PageRank (citing → cited), betweenness on the undirected
   view (exact up to 5,000 nodes, sampled from 500 sources above that), Louvain or Leiden
   communities;
3. collaboration graph: weighted PageRank, betweenness, communities;
4. community summaries (dominant topics).

Results are stored on nodes (`pagerank`, `betweenness`, `in_degree`, `out_degree`,
`community_id`, `analytics_computed_at`) and as `Community` nodes with `IN_COMMUNITY`
edges. Communities smaller than `min_community_size` (default 3) are not materialised.

Per-request computations never touch shared GDS projections: related-paper
recommendations run Personalized PageRank in-process on a bounded 2-hop neighbourhood,
and similarity (bibliographic coupling, co-citation) and shortest paths are plain Cypher.

## Observability

- JSON logs via structlog; every line in a request carries `request_id` (from a
  well-formed `X-Request-ID` header or generated), every ingestion line carries `job_id`.
- Access log with method, path, status and latency; per-query Neo4j timing at debug level.
- Keys that look like secrets are redacted from log events.
- Job and analytics-run records in PostgreSQL keep counters, durations and errors.

## Security (current)

- Secrets only from environment variables; `.env` is git-ignored; `SecretStr` in settings.
- Administrative endpoints (ingestion, analytics runs) require `X-Admin-Token` when
  `ADMIN_API_TOKEN` is set (constant-time comparison) and are disabled in production
  when it is not.
- Input validation through Pydantic on every endpoint; Cypher parameters for all values;
  whitelists for anything that cannot be a parameter.
- Security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`) and
  explicit CORS origins.
- Containers run as a non-root user.

Rate limiting, user authentication and prompt-injection defences arrive with the phases
that introduce public write paths and LLM features (see the roadmap).
