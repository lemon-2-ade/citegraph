import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";

import { errorResponse, mockApi, renderWithProviders } from "../test/utils";
import { paper } from "../test/fixtures";
import { SearchPage } from "./SearchPage";

const page = (route: string) =>
  renderWithProviders(
    <Routes>
      <Route path="/search" element={<SearchPage />} />
    </Routes>,
    route,
  );

describe("SearchPage", () => {
  it("shows which method found each paper", async () => {
    mockApi({
      "/api/search/papers": {
        query: "cheaper transformers",
        mode: "hybrid",
        semantic_available: true,
        note: null,
        hits: [
          { paper: paper({ id: "p1", title: "Reformer" }), score: 0.03, matched_by: ["keyword", "semantic"], keyword_rank: 2, semantic_rank: 1 },
          { paper: paper({ id: "p2", title: "Sparse Transformers" }), score: 0.01, matched_by: ["semantic"], keyword_rank: null, semantic_rank: 3 },
        ],
      },
    });
    page("/search?q=cheaper%20transformers");
    expect(await screen.findByRole("link", { name: "Reformer" })).toHaveAttribute("href", "/papers/p1");
    expect(screen.getByText("Keyword match · #2")).toBeInTheDocument();
    expect(screen.getAllByText(/Similar meaning · #/)).toHaveLength(2);
  });

  it("sends the chosen mode to the API", async () => {
    const { seen } = mockApi({
      "/api/search/papers": { query: "x", mode: "keyword", semantic_available: true, note: null, hits: [] },
    });
    page("/search?q=attention");
    await screen.findByText("No matching papers");
    await userEvent.click(screen.getByRole("button", { name: "Keyword" }));
    await screen.findByText("No matching papers");
    expect(seen.map((u) => u.searchParams.get("mode"))).toEqual(["hybrid", "keyword"]);
  });

  it("explains how to enable meaning search when embeddings are missing", async () => {
    mockApi({
      "/api/search/papers": () =>
        errorResponse(409, "semantic_unavailable", "Run `researchgraph embed` first."),
    });
    page("/search?q=attention&mode=semantic");
    expect(await screen.findByRole("alert")).toHaveTextContent("researchgraph embed");
  });

  it("shows the degraded-hybrid note", async () => {
    mockApi({
      "/api/search/papers": {
        query: "a b", mode: "hybrid", semantic_available: false,
        note: "Semantic search is unavailable: run embed. Showing keyword matches only.", hits: [],
      },
    });
    page("/search?q=ab");
    expect(await screen.findByText(/Showing keyword matches only/)).toBeInTheDocument();
  });

  it("asks for a query before searching", () => {
    const { seen } = mockApi({});
    page("/search");
    expect(screen.getByText("Type at least two characters to search")).toBeInTheDocument();
    expect(seen).toHaveLength(0);
  });
});
