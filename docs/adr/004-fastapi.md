# ADR-004: FastAPI for the API layer

**Status:** Accepted

## Context

The backend is Python (the AI/NLP and graph-analytics ecosystem is strongest there). The
API mostly waits on I/O — Neo4j, PostgreSQL, LLM providers — and needs typed request and
response models plus generated OpenAPI documentation for the frontend.

## Alternatives considered

- **Django + DRF.** Mature and batteries-included, but its ORM and admin assume a
  relational core, and async support is less pervasive.
- **Flask.** Minimal, but validation, OpenAPI and async all need extra libraries.
- **Node.js (NestJS/Express).** Good async story, but splits the codebase from the
  Python AI/graph tooling.

## Decision

Use **FastAPI** with **Pydantic v2** models.

## Consequences

- Request/response validation and OpenAPI docs (`/api/docs`) come from type hints.
- Native `async` works with the async Neo4j driver, asyncpg and httpx.
- CPU-heavy work (analytics, embeddings) must not run on the event loop; it goes to
  background workers (ADR-005) or a thread pool.
