import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

type Handler = ((url: URL) => Response) | Record<string, unknown> | unknown[];

/**
 * Replace global fetch with a route table keyed by URL path. Values are JSON bodies, or
 * functions returning a Response. Unmatched requests fail loudly (HTTP 599).
 */
export function mockApi(routes: Record<string, Handler>) {
  const seen: URL[] = [];
  const fn = vi.fn(async (input: Request | string | URL) => {
    const url = new URL(typeof input === "string" || input instanceof URL ? input : input.url, "http://test");
    seen.push(url);
    const handler = routes[decodeURIComponent(url.pathname)];
    if (handler === undefined) {
      return new Response(JSON.stringify({ error: { code: "unmocked", message: url.pathname } }), {
        status: 599,
        headers: { "content-type": "application/json" },
      });
    }
    if (typeof handler === "function") return (handler as (u: URL) => Response)(url);
    return new Response(JSON.stringify(handler), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fn);
  return { seen };
}

export function errorResponse(status: number, code: string, message: string): Response {
  return new Response(JSON.stringify({ error: { code, message } }), {
    status,
    headers: { "content-type": "application/json" },
  });
}

export function renderWithProviders(ui: ReactElement, route = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}
