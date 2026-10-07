import type { GraphSummary, PaperDetail, PaperSummary, SimilarPaper } from "../api/types";

export const paper = (overrides: Partial<PaperSummary> = {}): PaperSummary => ({
  id: "paper:1",
  title: "Attention Mechanisms for Sequence Models",
  year: 2017,
  venue: "Test Conf",
  authors: ["Ann Author", "Ben Builder"],
  doi: null,
  arxiv_id: null,
  citation_count: null,
  cited_by_in_graph: 3,
  pagerank: 0.0123,
  is_stub: false,
  ...overrides,
});

export const summary = (overrides: Partial<GraphSummary> = {}): GraphSummary => ({
  papers: 105,
  stub_papers: 2,
  authors: 457,
  citations: 380,
  topics: 23,
  venues: 12,
  institutions: 0,
  paper_communities: 6,
  author_communities: 48,
  analytics_computed_at: "2026-10-07T08:02:07+00:00",
  ...overrides,
});

export const detail = (overrides: Partial<PaperDetail> = {}): PaperDetail => ({
  id: "paper:1",
  title: "Attention Mechanisms for Sequence Models",
  abstract: "We study attention.",
  description: null,
  year: 2017,
  publication_date: null,
  doi: "10.1000/example",
  openalex_id: null,
  arxiv_id: null,
  url: null,
  language: null,
  citation_count: null,
  authors_complete: true,
  is_stub: false,
  sources: ["seed"],
  authors: [{ id: "author:1", name: "Ann Author", orcid: null, position: 0 }],
  venue: { id: "venue:1", name: "Test Conf", type: "conference" },
  topics: [{ id: "topic:1", name: "Graph Learning", score: 0.9 }],
  keywords: ["graphs"],
  cited_by_in_graph: 3,
  references_in_graph: 2,
  metrics: {
    pagerank: 0.0123,
    betweenness: null,
    in_degree: 3,
    out_degree: 2,
    community_id: "community:paper:1",
  },
  ...overrides,
});

export const similar = (overrides: Partial<SimilarPaper> = {}): SimilarPaper => ({
  paper: paper({ id: "paper:2", title: "A Similar Paper" }),
  method: "coupling",
  score: 2,
  shared: 2,
  explanation: "Shares 2 references with this paper.",
  ...overrides,
});

export const page = <T,>(items: T[], total = items.length, pageNumber = 1) => ({
  items,
  total,
  page: pageNumber,
  page_size: 20,
});
