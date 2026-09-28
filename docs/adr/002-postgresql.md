# ADR-002: PostgreSQL for application and operational data

**Status:** Accepted

## Context

Not all data is graph-shaped. Ingestion jobs and their checkpoints, users, reading
lists, search history and system configuration are row-oriented, need transactional
updates and are queried by key or by simple filters.

## Alternatives considered

- **Store everything in Neo4j.** Possible, but mixes operational state (job
  checkpoints written many times per second) with the knowledge graph, complicates
  backups and makes graph analytics projections noisier.
- **SQLite.** Adequate for a single process; unsuitable once the API and workers run
  as separate containers writing concurrently.
- **Redis as the job store.** Fast, but not a durable system of record for job history
  or user data.

## Decision

Use **PostgreSQL 16** via SQLAlchemy 2 (async, asyncpg driver) for application and
operational data. Redis remains a queue/cache only.

## Consequences

- Polyglot persistence: each store holds what it is good at. The ingestion pipeline
  records progress in PostgreSQL and writes knowledge into Neo4j; a job can resume from
  its last committed checkpoint.
- Cross-store consistency is eventual. Graph writes are idempotent `MERGE`s, so
  replaying a batch after a crash is safe.
- pgvector remains an option if vector search ever needs to move out of Neo4j (see the
  future ADR-003).
