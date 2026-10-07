# Architecture Decision Records

Each ADR records one significant decision: context, alternatives, the decision and its
consequences. ADRs are immutable once accepted; a later ADR supersedes an earlier one.

| ADR | Title | Status |
| --- | --- | --- |
| [001](001-neo4j.md) | Neo4j as the knowledge-graph store | Accepted |
| [002](002-postgresql.md) | PostgreSQL for application and operational data | Accepted |
| [004](004-fastapi.md) | FastAPI for the API layer | Accepted |
| [005](005-background-workers.md) | Arq for background processing | Accepted |
| [008](008-frontend-vite-spa.md) | Vite + React single-page app for the frontend | Accepted |

ADR-003 (hybrid graph + vector retrieval), ADR-006 (embedding model) and ADR-007
(LLM provider abstraction) will be written when those subsystems are built.
