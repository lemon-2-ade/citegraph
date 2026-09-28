# ADR-005: Arq for background processing

**Status:** Accepted

## Context

Ingestion, embedding generation, summarisation and graph analytics take seconds to hours
and must not block API requests. Jobs must be observable (status, progress, errors) and
resumable after a crash.

## Alternatives considered

- **Celery.** The most feature-rich option (routing, canvas, beat), but synchronous at its
  core; running async Neo4j/httpx code inside it needs event-loop bridging, and it brings
  substantial configuration surface.
- **RQ.** Simple, but synchronous and fork-per-job.
- **Dramatiq.** Solid, but also synchronous-first.
- **FastAPI `BackgroundTasks`.** Runs in the API process: work is lost on restart and
  competes with request handling.

## Decision

Use **Arq** (asyncio-native, Redis-backed) for task execution. **Durable job state lives
in PostgreSQL**, not in the queue: the queue only carries a job ID; the worker loads the
job, processes it in batches and commits a checkpoint after each batch.

## Consequences

- Workers share the same async code paths as the API (repositories, HTTP clients).
- Because progress is checkpointed in PostgreSQL, a job interrupted by a crash or
  redeploy resumes from its last checkpoint when re-enqueued; losing a Redis message
  never loses job history.
- Arq has a smaller ecosystem than Celery (no built-in canvas/workflows). Pipelines are
  composed explicitly in code, which is sufficient for this project.
- The CLI can run the same job synchronously without Redis, which keeps local and CI
  workflows simple.
