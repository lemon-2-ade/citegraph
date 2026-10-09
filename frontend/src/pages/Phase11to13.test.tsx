import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";

import { errorResponse, mockApi, renderWithProviders } from "../test/utils";
import { paper } from "../test/fixtures";
import { ReadingPathPage } from "./ReadingPathPage";
import { RecommendPage } from "./RecommendPage";
import { TrendsPage } from "./TrendsPage";

const hit = (id: string, title: string) => ({
  paper: paper({ id, title, year: 2020 }),
  score: 0.03,
  matched_by: ["keyword"],
  keyword_rank: 1,
  semantic_rank: null,
});

describe("RecommendPage", () => {
  it("builds a list, requests recommendations and shows why each was suggested", async () => {
    let body: unknown;
    mockApi({
      "/api/search/papers": { query: "attention", mode: "hybrid", hits: [hit("paper:1", "Attention Paper")], semantic_available: true, note: null },
      "/api/recommendations": (() => {
        return new Response(
          JSON.stringify({
            seeds: [paper({ id: "paper:1", title: "Attention Paper" })],
            recommendations: [
              {
                paper: paper({ id: "paper:7", title: "Next Read" }),
                score: 0.03,
                reasons: [{ kind: "similar_meaning", text: "Close in meaning to your list." }],
                linked_to: ["Attention Paper"],
              },
            ],
            semantic_available: false,
            note: "Citation links only.",
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        );
      }) as never,
    });
    const orig = globalThis.fetch;
    const spy = async (input: Request | string | URL) => {
      if (input instanceof Request && input.url.endsWith("/api/recommendations")) body = await input.clone().json();
      return orig(input as never);
    };
    // Wrap after mockApi so the request body can be inspected.
    globalThis.fetch = spy as typeof fetch;

    const user = userEvent.setup();
    renderWithProviders(<RecommendPage />);
    expect(screen.getByRole("button", { name: "Recommend papers" })).toBeDisabled();
    await user.type(screen.getByLabelText("Find a paper you have read"), "attention");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await user.click(await screen.findByRole("button", { name: "Add" }));
    expect(screen.getByText("Your reading list (1)")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Recommend papers" }));
    expect(await screen.findByRole("link", { name: "Next Read" })).toBeInTheDocument();
    expect(screen.getByText("Close in meaning to your list.")).toBeInTheDocument();
    expect(screen.getByText(/Linked to: Attention Paper/)).toBeInTheDocument();
    expect(screen.getByText("Citation links only.")).toBeInTheDocument();
    expect(body).toEqual({ paper_ids: ["paper:1"], limit: 10 });
  });
});

describe("TrendsPage", () => {
  const trend = (over = {}) => ({
    topic_id: "topic:g",
    name: "Graph Learning",
    total: 5,
    series: [{ year: 2020, papers: 1 }, { year: 2023, papers: 4 }],
    recent: 4,
    previous: 1,
    share_recent: 0.4,
    share_previous: 0.1,
    growth: 3.2,
    label: "rising",
    ...over,
  });
  const payload = (topics: unknown[]) => ({
    first_year: 2020, last_year: 2023, window: 3, recent_years: [2021, 2022, 2023], previous_years: [2018, 2019, 2020],
    topics, note: "Trends describe the papers in this graph.",
  });

  it("shows each topic's label as text with its numbers", async () => {
    mockApi({ "/api/trends/topics": payload([trend(), trend({ topic_id: "t2", name: "Old Topic", label: "declining", growth: 0.4 })]) });
    renderWithProviders(<TrendsPage />);
    const row = (await screen.findByRole("link", { name: "Graph Learning" })).closest("tr")!;
    expect(within(row).getByText("Rising")).toBeInTheDocument();
    expect(within(row).getByText("3.20×")).toBeInTheDocument();
    expect(within(row).getByRole("img")).toHaveAccessibleName(/2023 4/);
    expect(screen.getByText("Declining")).toBeInTheDocument();
    expect(screen.getByText("Trends describe the papers in this graph.")).toBeInTheDocument();
  });

  it("explains an empty result", async () => {
    mockApi({ "/api/trends/topics": payload([]) });
    renderWithProviders(<TrendsPage />);
    expect(await screen.findByText("Not enough data for trends")).toBeInTheDocument();
  });
});

describe("ReadingPathPage", () => {
  const path = {
    focus: "Topic: Graphs",
    candidates: 12,
    note: "Order follows citations.",
    steps: [
      { position: 1, paper: paper({ id: "paper:a", title: "Foundation" }), cited_by_on_path: 2, builds_on: [], reason: "Cited by 2 other paper(s) on this path, so it is foundational here." },
      { position: 2, paper: paper({ id: "paper:b", title: "Follow-up" }), cited_by_on_path: 0, builds_on: ["Foundation"], reason: "Builds on 1 earlier paper(s) on the path." },
    ],
  };

  function renderAt(url: string) {
    return renderWithProviders(
      <Routes>
        <Route path="/reading-path" element={<ReadingPathPage />} />
      </Routes>,
      url,
    );
  }

  it("asks for a topic when none is chosen", async () => {
    mockApi({ "/api/topics": { items: [], total: 0, page: 1, page_size: 100 } });
    renderAt("/reading-path");
    expect(await screen.findByText("Pick a topic")).toBeInTheDocument();
  });

  it("lists papers in reading order with reasons", async () => {
    mockApi({
      "/api/topics": { items: [{ id: "topic:g", name: "Graphs", description: null, paper_count: 3 }], total: 1, page: 1, page_size: 100 },
      "/api/reading-path": path,
    });
    renderAt("/reading-path?topic_id=topic:g");
    const items = await screen.findAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Foundation");
    expect(items[1]).toHaveTextContent("Builds on: Foundation");
    expect(screen.getByText(/Considered 12 papers/)).toBeInTheDocument();
  });

  it("shows errors", async () => {
    mockApi({
      "/api/topics": { items: [], total: 0, page: 1, page_size: 100 },
      "/api/reading-path": () => errorResponse(404, "not_found", "Topic 'x' not found"),
    });
    renderAt("/reading-path?topic_id=x");
    expect(await screen.findByText(/not found/)).toBeInTheDocument();
  });
});
