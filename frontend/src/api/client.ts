import createClient from "openapi-fetch";

import { ApiError, toApiError } from "./errors";
import type { paths } from "./schema";

/**
 * Typed client generated from the backend's OpenAPI schema. Paths already include the
 * `/api` prefix, so the base URL is the page origin (Vite and nginx both proxy `/api`).
 * An absolute origin is used because `Request` objects cannot hold relative URLs outside a
 * browser. `fetch` is looked up per call so tests can replace it.
 */
export const api = createClient<paths>({
  baseUrl: typeof window === "undefined" ? "" : window.location.origin,
  fetch: (request) => globalThis.fetch(request),
});

interface Result<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** Resolve an openapi-fetch call to its data, or throw an ApiError. */
export async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  let result: Result<T>;
  try {
    result = await call;
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the API. Is the backend running?");
  }
  if (result.error !== undefined || result.data === undefined) {
    throw toApiError(result.response.status, result.error);
  }
  return result.data;
}
