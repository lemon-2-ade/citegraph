import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

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

export function useSearch(text: string) {
  const q = text.trim();
  return useQuery({
    queryKey: ["search", q],
    queryFn: () => unwrap(api.GET("/api/search", { params: { query: { q, limit: 6 } } })),
    enabled: q.length >= 2,
    staleTime: STALE_MS,
  });
}

export function useAuthor(id: string) {
  return useQuery({
    queryKey: ["author", id],
    queryFn: () => unwrap(api.GET("/api/authors/{author_id}", { params: { path: { author_id: id } } })),
    staleTime: STALE_MS,
    retry: (count, error) => !(error instanceof ApiError && error.isNotFound) && count < 2,
  });
}

export function useInfluentialAuthors(limit = 25) {
  return useQuery({
    queryKey: ["influential", "author", "paper_count", limit],
    queryFn: () =>
      unwrap(
        api.GET("/api/analytics/influential", {
          params: { query: { entity: "author", metric: "paper_count", limit } },
        }),
      ),
    staleTime: STALE_MS,
  });
}

export function useTopics() {
  return useQuery({
    queryKey: ["topics"],
    queryFn: () => unwrap(api.GET("/api/topics", { params: { query: { page: 1, page_size: 100 } } })),
    staleTime: STALE_MS,
  });
}

export function useTopic(id: string) {
  return useQuery({
    queryKey: ["topic", id],
    queryFn: () => unwrap(api.GET("/api/topics/{topic_id}", { params: { path: { topic_id: id } } })),
    staleTime: STALE_MS,
    retry: (count, error) => !(error instanceof ApiError && error.isNotFound) && count < 2,
  });
}

export function useCommunities(scope: "papers" | "authors") {
  return useQuery({
    queryKey: ["communities", scope],
    queryFn: () => unwrap(api.GET("/api/communities", { params: { query: { scope, page_size: 50 } } })),
    staleTime: STALE_MS,
  });
}

export function useCommunity(id: string) {
  return useQuery({
    queryKey: ["community", id],
    queryFn: () =>
      unwrap(api.GET("/api/communities/{community_id}", { params: { path: { community_id: id } } })),
    staleTime: STALE_MS,
    retry: (count, error) => !(error instanceof ApiError && error.isNotFound) && count < 2,
  });
}

export type SearchMode = "keyword" | "semantic" | "hybrid";

export function usePaperSearch(text: string, mode: SearchMode) {
  const q = text.trim();
  return useQuery({
    queryKey: ["search", "papers", q, mode],
    queryFn: () =>
      unwrap(api.GET("/api/search/papers", { params: { query: { q, mode, limit: 20 } } })),
    enabled: q.length >= 2,
    placeholderData: keepPreviousData,
    staleTime: STALE_MS,
    // A 409 means embeddings are not set up; retrying will not change that.
    retry: (count, error) => !(error instanceof ApiError && error.status === 409) && count < 2,
  });
}

export function useSemanticSimilar(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ["semantic-similar", id],
    queryFn: () =>
      unwrap(
        api.GET("/api/papers/{paper_id}/semantic-similar", {
          params: { path: { paper_id: id }, query: { limit: 8 } },
        }),
      ),
    enabled,
    staleTime: STALE_MS,
    retry: false,
  });
}

/** The stored AI insight for a paper; resolves to null (not an error) when none exists yet. */
export function usePaperInsight(id: string) {
  return useQuery({
    queryKey: ["insight", id],
    queryFn: async () => {
      try {
        return await unwrap(
          api.GET("/api/papers/{paper_id}/insight", { params: { path: { paper_id: id } } }),
        );
      } catch (error) {
        if (error instanceof ApiError && error.isNotFound) return null;
        throw error;
      }
    },
    staleTime: STALE_MS,
    retry: false,
  });
}

export function useGenerateInsight(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (force: boolean) =>
      unwrap(
        api.POST("/api/papers/{paper_id}/insight", {
          params: { path: { paper_id: id }, query: { force } },
        }),
      ),
    onSuccess: (data) => client.setQueryData(["insight", id], data),
  });
}
