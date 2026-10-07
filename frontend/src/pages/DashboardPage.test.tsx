import { screen } from "@testing-library/react";

import { errorResponse, mockApi, renderWithProviders } from "../test/utils";
import { page, paper, summary } from "../test/fixtures";
import { DashboardPage } from "./DashboardPage";

vi.mock("../graph/GraphCanvas", () => ({
  GraphCanvas: () => <div data-testid="graph-canvas" />, // jsdom has no canvas
}));

const EXTRA = {
  "/api/analytics/years": [
    { year: 2017, papers: 4 },
    { year: 2018, papers: 7 },
  ],
  "/api/communities": [
    { id: "c:1", rank: 1, size: 40, label: "Graph learning", algorithm: "louvain", scope: "papers", computed_at: null, top_topics: ["GNN"] },
  ],
  "/api/graph/overview": { nodes: [], edges: [], focus: null, truncated: false, total_papers: 0, note: "" },
};

const NOTE = "PageRank measures structural influence inside this citation graph.";

describe("DashboardPage", () => {
  it("shows graph counts, the metric caveat and ranked papers", async () => {
    mockApi({
      ...EXTRA,
      "/api/analytics/summary": summary(),
      "/api/analytics/influential": {
        entity: "paper",
        metric: "pagerank",
        note: NOTE,
        papers: [{ paper: paper({ title: "Top Ranked Paper" }), score: 0.05 }],
        authors: [],
      },
    });
    renderWithProviders(<DashboardPage />);

    expect(await screen.findByText("457")).toBeInTheDocument(); // authors tile
    expect(screen.getByText(/2 additional papers are stubs/)).toBeInTheDocument();
    expect(await screen.findByText("Top Ranked Paper")).toBeInTheDocument();
    expect(screen.getByText(NOTE)).toBeInTheDocument();
  });

  it("explains how to load data when the graph is empty", async () => {
    mockApi({
      ...EXTRA,
      "/api/analytics/summary": summary({ papers: 0, stub_papers: 0, authors: 0 }),
      "/api/analytics/influential": { entity: "paper", metric: "pagerank", note: NOTE, papers: [], authors: [] },
    });
    renderWithProviders(<DashboardPage />);
    expect(await screen.findByText("The graph is empty")).toBeInTheDocument();
    expect(screen.getByText(/No rankings yet/)).toBeInTheDocument();
  });

  it("shows an error with a retry when the API is unavailable", async () => {
    mockApi({
      ...EXTRA,
      "/api/analytics/summary": () => errorResponse(503, "dependency_unavailable", "Neo4j is unavailable"),
      "/api/analytics/influential": { entity: "paper", metric: "pagerank", note: NOTE, papers: [], authors: [] },
    });
    renderWithProviders(<DashboardPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Neo4j is unavailable");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("shows communities and the per-year chart", async () => {
    mockApi({
      ...EXTRA,
      "/api/analytics/summary": summary(),
      "/api/analytics/influential": { entity: "paper", metric: "pagerank", note: NOTE, papers: [], authors: [] },
    });
    renderWithProviders(<DashboardPage />);
    expect(await screen.findByText("Graph learning")).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: /ingested papers by publication year/ })).toBeInTheDocument();
  });

  it("reports an unreachable backend", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    renderWithProviders(<DashboardPage />);
    expect((await screen.findAllByRole("alert"))[0]).toHaveTextContent(/Cannot reach the API/);
  });

  it("lists page content with a link to the papers browser", async () => {
    mockApi({
      ...EXTRA,
      "/api/analytics/summary": summary(),
      "/api/analytics/influential": {
        entity: "paper",
        metric: "pagerank",
        note: NOTE,
        papers: [{ paper: paper(), score: 0.05 }],
        authors: [],
      },
      "/api/papers": page([paper()]),
    });
    renderWithProviders(<DashboardPage />);
    expect(await screen.findByRole("link", { name: /All papers by PageRank/ })).toHaveAttribute(
      "href",
      "/papers?sort=pagerank",
    );
  });
});
