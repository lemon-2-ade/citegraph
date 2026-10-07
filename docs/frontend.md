# Frontend

A Vite + React + TypeScript single-page app ([ADR-008](adr/008-frontend-vite-spa.md)).

## What exists (Phases 5 and 5b)

| Route | Shows |
| --- | --- |
| `/` | Stat tiles, a graph preview, research communities, papers per year, and the most structurally influential papers (with the API's PageRank caveat) |
| `/graph` | **Graph explorer**: interactive citation graph (Cytoscape.js, fCoSE layout, lazy-loaded). Node size = PageRank or cited-by; colour = research community or year; node-count slider, 1/2-hop focus mode (`?focus=<id>`), labels, zoom/fit/re-layout, side panel for the selected paper, and a table view as the accessible alternative. State lives in the URL |
| `/papers` | Paper browser: year range, sort (year, PageRank, cited-by-in-graph), pagination. Filters live in the URL |
| `/papers/:id` | Authors, venue, abstract, topics, graph metrics, citing and cited papers, structurally similar papers (shared references, co-citation) and papers reachable through citation paths, and an embedded citation-neighbourhood graph |

Every view has loading, empty and error states. Stub papers (cited but not yet fetched) are
labelled. Abstracts and titles come from external sources and are rendered as plain text,
never as HTML.

Not built yet: author, topic and community pages, search,
and everything AI-related.

## Layout

```text
frontend/src/
  api/          generated schema.d.ts, typed client, query hooks, error normalisation
  components/   Layout (sidebar), PaperList, Charts, Pagination, loading/empty/error views
  graph/        GraphCanvas (Cytoscape), colour/size encodings, legend, selection panel
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

## Graph visualisation

Colour follows the entity, not its rank in the current view: a community keeps the same
colour whatever subgraph is shown (global community rank 1-7 map to fixed palette slots;
the rest are grey "Other"). Because the categorical palette only separates three hues for
every pair, identity is never colour-alone: the legend, tooltip and selection panel all name
the community. Light and dark palettes are separate token sets in `styles/tokens.css`.
The backend caps responses (`/api/graph/overview`, `/api/graph/neighborhood/{id}`) at 300 nodes.
