# Frontend

A Vite + React + TypeScript single-page app ([ADR-008](adr/008-frontend-vite-spa.md)).

## What exists (Phase 5)

| Route | Shows |
| --- | --- |
| `/` | Graph counts, when analytics last ran, most structurally influential papers (with the API's PageRank caveat) |
| `/papers` | Paper browser: year range, sort (year, PageRank, cited-by-in-graph), pagination. Filters live in the URL |
| `/papers/:id` | Authors, venue, abstract, topics, graph metrics, citing and cited papers, structurally similar papers (shared references, co-citation) and papers reachable through citation paths |

Every view has loading, empty and error states. Stub papers (cited but not yet fetched) are
labelled. Abstracts and titles come from external sources and are rendered as plain text,
never as HTML.

Not built yet: author, topic and community pages, graph visualisation (Phase 6), search,
and everything AI-related.

## Layout

```text
frontend/src/
  api/          generated schema.d.ts, typed client, query hooks, error normalisation
  components/   Layout, PaperList, Pagination, loading/empty/error views
  pages/        one file per route, with tests beside them
  lib/          formatting helpers
  test/         mocked-fetch helpers and fixtures
```

## Running it

```bash
# whole stack (UI on http://localhost:8080, nginx proxies /api to the backend)
docker compose up -d --build

# development: backend on :8000, then
make frontend-install
make frontend-dev            # http://localhost:5173, /api proxied to localhost:8000
```

Set `VITE_DEV_API_TARGET` to proxy the dev server somewhere other than `localhost:8000`.

## API types

`frontend/openapi.json` and `frontend/src/api/schema.d.ts` are generated from the backend and
committed. After changing an API model or route:

```bash
make api-types
```

CI regenerates both and fails if they differ from what is committed, so a backend change
that the UI does not know about cannot merge silently.

## Checks

```bash
make frontend-check          # typecheck, eslint, vitest
cd frontend && npm run build # type-check + production bundle
```

Component tests replace `fetch` with a route table (`src/test/utils.tsx`) and assert on what
the user sees and on the query parameters sent. They do not run a browser; layout and styling
are checked by eye.
