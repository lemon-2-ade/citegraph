# ADR-008: Vite + React single-page app for the frontend

**Status:** Accepted

## Context

The web client explores a citation graph: filterable paper lists, paper detail pages,
dashboards, a graph visualisation (Phase 6) and a streaming chat over the graph-aware RAG
pipeline (later phases). The FastAPI backend already owns all server-side logic —
validation, query building, authorisation, background jobs — and publishes a typed
OpenAPI contract (ADR-004). The product is an interactive tool, not a content site; no
requirement calls for search-engine indexing of individual pages.

## Alternatives considered

- **Next.js (App Router).** Server rendering and React Server Components help SEO and
  first-paint for public content. Here it would add a second server runtime (Node) next to
  FastAPI, blur where data fetching and authorisation live, and add a deployment unit,
  while the interactive parts (graph canvas, chat, filters) are client-rendered anyway.
- **Vite SPA.** Static build output, fast dev server, no second backend. All data comes
  from FastAPI through one typed client.
- **Server-rendered templates (Jinja/HTMX).** Simple, but a poor fit for a force-directed
  graph and streaming chat.

## Decision

Use **Vite + React + TypeScript (strict)**, served as static files behind nginx, which also
proxies `/api` to the backend so the browser sees one origin.

Supporting choices:

- **TanStack Query** for server state (caching, retries, loading and error states);
  React state for UI state only.
- **React Router** for routing; filter state lives in the URL so views are shareable.
- **openapi-typescript + openapi-fetch**: types are generated from the backend's OpenAPI
  schema, so a breaking API change fails type-checking instead of failing at runtime. The
  schema is exported offline by a backend script and the generated file is committed; CI
  fails if it is stale.
- **Vitest + Testing Library** for component tests against a mocked API layer.
- Plain CSS with design tokens (no component framework) to keep the bundle small and the
  look consistent; theming via CSS variables with light and dark modes.

## Consequences

- One deployment story: static assets plus the existing API.
- No server-side rendering. If shareable, indexable paper pages become a requirement, a
  small server-rendered layer can be added for those routes without rewriting the SPA.
- The browser talks only to `/api`; CORS is needed only for the dev server, which proxies.
- The generated schema file is a build artefact kept in git; regenerating it is one
  command (`make api-types`).
