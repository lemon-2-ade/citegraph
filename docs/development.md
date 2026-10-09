# Development

## Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Docker with Compose v2 (for Neo4j, PostgreSQL and Redis)
- Node.js 20+ (frontend, and the Cypher lint step)

## First run

```bash
cp .env.example .env          # set NEO4J_PASSWORD, POSTGRES_PASSWORD, ADMIN_API_TOKEN, ...
docker compose up -d --build  # neo4j (with GDS), postgres, redis, backend, worker

docker compose exec backend researchgraph init      # constraints, indexes, tables
docker compose exec backend researchgraph seed      # curated sample dataset
docker compose exec backend researchgraph analyze   # PageRank, centrality, communities

open http://localhost:8080                          # web UI
open http://localhost:8000/api/docs                 # OpenAPI UI
open http://localhost:7474                          # Neo4j Browser
```

Expanding the graph with real data (needs internet access from the containers):

```bash
docker compose exec backend researchgraph ingest \
  --query "graph neural networks fraud detection" --max-results 300 --hydrate 100
docker compose exec backend researchgraph analyze
```

## AI features

```bash
docker compose exec backend researchgraph embed      # vectors + index (OpenAI if a key is set, else local)
docker compose exec backend researchgraph insights --limit 20   # AI summaries; skips finished papers
docker compose exec backend researchgraph eval retrieval         # quality numbers (see docs/evaluation.md)
```

`OPENAI_API_KEY` in `.env` enables hosted embeddings and the LLM features (`LLM_PROVIDER` can also
be `gemini` or `ollama`). In development the LLM endpoints are open when `ADMIN_API_TOKEN` is
unset; otherwise send it as `X-Admin-Token`, or set `PUBLIC_AI=true`.

Switching the embedding model requires `researchgraph embed --rebuild`.

## Performance

`python backend/scripts/loadtest.py --base http://localhost:8000` prints p50/p95 latency for the
common read endpoints against your running stack (add `--with-ai` to include the paid ones).
`make test` includes guard tests that fail if a pure-Python hot path turns quadratic; they say
nothing about Neo4j latency, which depends on your data and hardware.

## Running the backend outside Docker

```bash
docker compose up -d neo4j postgres redis
cd backend
uv sync
uv run researchgraph init
uv run uvicorn app.main:app --reload       # API on :8000
uv run arq app.workers.tasks.WorkerSettings  # worker (separate shell)
```

The settings in `.env` for `NEO4J_URI`, `DATABASE_URL` and `REDIS_URL` point at
`localhost` for this mode.

## Tests

```bash
make test              # unit tests (no services needed)
make lint              # ruff, ruff format --check, mypy --strict
make lint-cypher       # parse + semantically check every Cypher query
```

Integration tests talk to real databases and **wipe them**. Point them at the Compose
services (or dedicated test instances), never at data you care about:

```bash
cd backend
RG_TEST_NEO4J_URI=bolt://localhost:7687 RG_TEST_NEO4J_PASSWORD=$NEO4J_PASSWORD \
RG_TEST_DATABASE_URL=postgresql+asyncpg://researchgraph:$POSTGRES_PASSWORD@localhost:5432/researchgraph \
uv run pytest -m integration
```

Tests that need a service whose variable is unset are skipped. The GDS analytics test is
additionally skipped when the Graph Data Science plugin is absent.

### Test layout

| Directory | What it covers |
| --- | --- |
| `tests/unit` | Pure logic (normalisation, resolution, algorithms), HTTP retry/rate limiting, OpenAlex parsing against recorded-shape fixtures, pipeline checkpoint/resume with SQLite, API routes against a scripted fake graph, CLI |
| `tests/integration` | Neo4j client, schema, loader (idempotency, stub filling, node merging, author unification), seed load, NetworkX and GDS analytics; PostgreSQL job/run repositories |

`tests/fakes.py::ScriptedGraph` returns canned rows keyed by the query *label* passed to
`GraphClient.read/write`; tests assert on the parameters it recorded.

### Cypher lint

`backend/scripts/dump_cypher.py` collects every query the backend can issue — module
constants plus queries captured by driving repositories, the loader and dynamic query
builders against a recording fake — and `scripts/cypher-lint/lint.mjs` checks each one with
Neo4j's `@neo4j-cypher/language-support` parser (syntax and semantic analysis, e.g.
undefined variables). It does not know which procedures (GDS) exist, and it cannot catch
runtime behaviour; integration tests cover that.

## Frontend

`make frontend-install && make frontend-dev` starts the Vite dev server on :5173 with `/api`
proxied to the backend. See [frontend.md](frontend.md).

## Conventions

- Type hints everywhere; `mypy --strict` must pass.
- Every Cypher query gets a short `label=` for logs and tests; values are always
  parameters.
- Commit messages follow Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, …).
