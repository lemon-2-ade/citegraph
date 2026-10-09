# Security

This is a research tool, not a hardened multi-tenant service. This page lists what is protected,
how, and what is deliberately left to the deployer.

## Assets and threats

| Asset | Threat | Controls |
| --- | --- | --- |
| LLM and embedding budget | Anyone calling `/api/ask`, `/api/query`, `/api/papers/{id}/insight` in a loop | Access gate (`ADMIN_API_TOKEN`, or `PUBLIC_AI=true` to opt in); per-client rate limit (`RATE_LIMIT_AI_PER_MINUTE`, default 12); request body cap |
| The graph | A model-written query that writes, deletes, or runs a procedure | Three layers, none trusting the model: static allow-list, Neo4j `EXPLAIN` read-only check, read transaction with a timeout and row cap ([ADR-009](adr/009-natural-language-to-cypher.md)) |
| Answer integrity | Text in a paper abstract that tells the model what to say (prompt injection) | Source text is delimited and declared untrusted; no tools are exposed to the model; output is rendered as plain text; citation markers are verified server-side |
| Secrets | API keys or passwords in logs, errors or responses | `SecretStr` settings; provider errors never include response bodies or headers; `.env` is git-ignored |
| Availability | Oversized or abusive requests | Body size limit (413), rate limits (429, with `Retry-After`), query timeout, capped row counts |
| Browser users | XSS, clickjacking, MIME sniffing | React renders all external text as text; CSP on the SPA and the API; `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`; HSTS in production |
| Infrastructure | Databases reachable from the network | Compose publishes Neo4j, PostgreSQL, Redis and the backend on `127.0.0.1` only; the backend container runs as a non-root user |

## Access model

- Read-only data endpoints are open. Put the app behind your own authentication if the data is
  not meant to be public.
- Administrative endpoints (ingestion, analytics runs) require `X-Admin-Token`. In development with
  no token they are open; **in production with no token they are disabled**.
- LLM-backed endpoints follow the same rule, except that `PUBLIC_AI=true` makes them public (still
  rate limited). Use that for a demo; for anything else keep the token.
- There are no user accounts. The admin token is a shared secret compared in constant time. Rotate
  it by changing the environment variable.

## Rate limiting

Sliding windows per client address, in process memory. Behind the bundled nginx the backend reads
the address from `X-Forwarded-For` (`TRUST_FORWARDED_FOR=true`); nginx overwrites that header and
the backend port is bound to localhost, so clients cannot spoof it. **Do not enable
`TRUST_FORWARDED_FOR` when the backend is directly reachable**, and note that limits are not
shared between replicas.

## Known gaps

- No per-user quotas or authentication; a determined user can rotate IPs to spread requests.
- A prompt-injected abstract can still skew an answer's wording. The defences make it detectable
  (sources and excerpts are shown) rather than impossible.
- The Cypher validator is a conservative subset, not a full parser. `EXPLAIN` and the read
  transaction are the backstops; for production create a Neo4j user with read-only privileges and
  point the app at it.
- No audit log of who asked what; request IDs and structured logs exist, but question text is not
  stored.
- Dependencies are audited in CI (`pip-audit`, `npm audit`) when the workflow runs; transitive
  advisories without a fix will fail the job until triaged.

## Reporting

Open a private security advisory on the repository rather than a public issue.
