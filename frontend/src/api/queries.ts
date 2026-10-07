import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import { ApiError } from "./errors";
import type { paths } from "./schema";

type Query<P extends keyof paths> = paths[P] extends {
  get: { parameters: { query?: infer Q } };
}
  ? NonNullable<Q>
  : never;

export type PaperListParams = Query<"/api/papers">;
export type PaperSort = NonNullable<PaperListParams["sort"]>;

const STALE_MS = 30_000;

export function useSummary() {
  return useQuery({
    queryKey: ["summary"],
    queryFn: () => unwrap(api.GET("/api/analytics/summary")),
    staleTime: STALE_MS,
  });
}

export function useInfluentialPapers(limit = 10) {
  return useQuery({
    queryKey: ["influential", "paper", "pagerank", limit],
    queryFn: () =>
      unwrap(
        api.GET("/api/analytics/influential", {
          params: { query: { entity: "paper", metric: "pagerank", limit } },
        }),
      ),
    staleTime: STALE_MS,
  });
}

export function usePapers(params: PaperListParams) {
  return useQuery({
    queryKey: ["papers", params],
    queryFn: () => unwrap(api.GET("/api/papers", { params: { query: params } })),
    placeholderData: keepPreviousData,
    staleTime: STALE_MS,
  });
}

export function usePaper(id: string) {
  return useQuery({
    queryKey: ["paper", id],
    queryFn: () => unwrap(api.GET("/api/papers/{paper_id}", { params: { path: { paper_id: id } } })),
    staleTime: STALE_MS,
    // A missing paper will not appear on retry.
    retry: (count, error) => !(error instanceof ApiError && error.isNotFound) && count < 2,
  });
}

export function useCitations(id: string, page: number) {
  return useQuery({
    queryKey: ["citations", id, page],
    queryFn: () =>
      unwrap(
        api.GET("/api/papers/{paper_id}/citations", {
          params: { path: { paper_id: id }, query: { page, page_size: 10 } },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function useReferences(id: string, page: number) {
  return useQuery({
    queryKey: ["references", id, page],
    queryFn: () =>
      unwrap(
        api.GET("/api/papers/{paper_id}/references", {
          params: { path: { paper_id: id }, query: { page, page_size: 10 } },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function useSimilarPapers(id: string, method: "coupling" | "cocitation") {
  return useQuery({
    queryKey: ["similar", id, method],
    queryFn: () =>
      unwrap(
        api.GET("/api/papers/{paper_id}/similar", {
          params: { path: { paper_id: id }, query: { method, limit: 8 } },
        }),
      ),
  });
}

export function useRelatedPapers(id: string) {
  return useQuery({
    queryKey: ["related", id],
    queryFn: () =>
      unwrap(
        api.GET("/api/papers/{paper_id}/related", {
          params: { path: { paper_id: id }, query: { limit: 8 } },
        }),
      ),
  });
}

export function usePapersPerYear() {
  return useQuery({
    queryKey: ["papers-per-year"],
    queryFn: () => unwrap(api.GET("/api/analytics/years")),
    staleTime: STALE_MS,
  });
}

export function usePaperCommunities() {
  return useQuery({
    queryKey: ["communities", "papers"],
    queryFn: () =>
      unwrap(api.GET("/api/communities", { params: { query: { scope: "papers", page_size: 50 } } })),
    staleTime: STALE_MS,
  });
}

export function useGraphOverview(limit: number) {
  return useQuery({
    queryKey: ["graph", "overview", limit],
    queryFn: () => unwrap(api.GET("/api/graph/overview", { params: { query: { limit } } })),
    placeholderData: keepPreviousData,
    staleTime: STALE_MS,
  });
}

export function useGraphNeighbourhood(id: string | null, depth: 1 | 2, limit: number) {
  return useQuery({
    queryKey: ["graph", "neighborhood", id, depth, limit],
    queryFn: () =>
      unwrap(
        api.GET("/api/graph/neighborhood/{paper_id}", {
          params: { path: { paper_id: id ?? "" }, query: { depth, limit } },
        }),
      ),
    enabled: id !== null,
    placeholderData: keepPreviousData,
    staleTime: STALE_MS,
    retry: (count, error) => !(error instanceof ApiError && error.isNotFound) && count < 2,
  });
}
