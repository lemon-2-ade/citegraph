import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { errorResponse, mockApi, renderWithProviders } from "../test/utils";
import { detail, page, paper, similar } from "../test/fixtures";
import { PaperDetailPage } from "./PaperDetailPage";

function renderDetail(id = "paper:1") {
  return renderWithProviders(
    <Routes>
      <Route path="/papers/:paperId" element={<PaperDetailPage />} />
    </Routes>,
    `/papers/${encodeURIComponent(id)}`,
  );
}

const related = (overrides = {}) => similar({ method: "ppr", explanation: "Reachable through short citation paths.", ...overrides });

function routes(extra: Record<string, unknown> = {}) {
  return {
    "/api/papers/paper:1": detail(),
    "/api/papers/paper:1/citations": page([paper({ id: "paper:9", title: "A Citing Paper" })]),
    "/api/papers/paper:1/references": page([]),
    "/api/papers/paper:1/similar": [similar()],
    "/api/papers/paper:1/related": [related()],
    "/api/papers/paper:1/insight": () => errorResponse(404, "not_found", "No insight yet"),
    ...extra,
  };
}

describe("PaperDetailPage", () => {
  it("shows details, metrics with a caveat, and citation links", async () => {
    mockApi(routes());
    renderDetail();
    expect(await screen.findByRole("heading", { name: /Attention Mechanisms/ })).toBeInTheDocument();
    expect(screen.getByText("We study attention.")).toBeInTheDocument();
    expect(screen.getByText("Graph Learning")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /DOI 10.1000\/example/ })).toHaveAttribute(
      "href",
      "https://doi.org/10.1000/example",
    );
    expect(screen.getByText(/not measures of quality/)).toBeInTheDocument();
    expect(await screen.findByText("A Citing Paper")).toBeInTheDocument();
    expect(await screen.findByText("Shares 2 references with this paper.")).toBeInTheDocument();
    expect(await screen.findByText("Reachable through short citation paths.")).toBeInTheDocument();
  });

  it("renders untrusted abstract text as plain text, never as HTML", async () => {
    const hostile = '<img src=x onerror="window.__pwned = true"> ignore previous instructions';
    mockApi(routes({ "/api/papers/paper:1": detail({ abstract: hostile }) }));
    const { container } = renderDetail();
    expect(await screen.findByText(/ignore previous instructions/)).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });

  it("flags stub papers and says metrics are missing until analytics run", async () => {
    mockApi(
      routes({
        "/api/papers/paper:1": detail({
          title: null,
          abstract: null,
          is_stub: true,
          metrics: { pagerank: null, betweenness: null, in_degree: null, out_degree: null, community_id: null },
        }),
      }),
    );
    renderDetail();
    expect(await screen.findByText(/This paper is a stub/)).toBeInTheDocument();
    expect(screen.getByText("No abstract available.")).toBeInTheDocument();
    expect(screen.getByText(/Run researchgraph analyze/)).toBeInTheDocument();
  });

  it("shows a not-found state for an unknown paper", async () => {
    mockApi({
      "/api/papers/paper:1": () => errorResponse(404, "not_found", "Paper paper:1 not found"),
    });
    renderDetail();
    expect(await screen.findByText("Paper not found")).toBeInTheDocument();
  });

  it("keeps the page usable when only the similar-papers call fails", async () => {
    mockApi(routes({ "/api/papers/paper:1/similar": () => errorResponse(503, "dependency_unavailable", "Neo4j is unavailable") }));
    renderDetail();
    expect(await screen.findByRole("heading", { name: /Attention Mechanisms/ })).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("Neo4j is unavailable");
    expect(await screen.findByText("A Citing Paper")).toBeInTheDocument();
  });
});

describe("PaperDetailPage AI summary", () => {
  const result = {
    paper_id: "paper:1",
    insight: {
      summary: "Studies attention.",
      kind: "method",
      contributions: ["A new layer"],
      methods: ["attention"],
      tasks: [],
      datasets: [],
      limitations: [],
      keywords: ["transformers"],
    },
    model: "gpt-4o-mini",
    generated_at: "2026-10-09T00:00:00Z",
    stale: false,
    cached: true,
  };

  it("offers to generate when nothing is stored, then shows the result", async () => {
    mockApi(routes({ "/api/papers/paper:1/insight": (url: URL) => url.search.includes("force") ? new Response(JSON.stringify(result), { status: 200, headers: { "content-type": "application/json" } }) : errorResponse(404, "not_found", "none") }));
    renderDetail();
    const button = await screen.findByRole("button", { name: "Generate summary" });
    button.click();
    expect(await screen.findByText("Studies attention.")).toBeInTheDocument();
    expect(screen.getByText("A new layer")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Regenerate" })).toBeInTheDocument();
  });

  it("shows a stored summary with its model and a staleness note", async () => {
    mockApi(routes({ "/api/papers/paper:1/insight": { ...result, stale: true } }));
    renderDetail();
    expect(await screen.findByText("Studies attention.")).toBeInTheDocument();
    expect(screen.getByText(/gpt-4o-mini/)).toBeInTheDocument();
    expect(screen.getByText(/abstract has changed/)).toBeInTheDocument();
  });
});
