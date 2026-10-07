import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "./App";
import { page, paper, summary } from "./test/fixtures";
import { mockApi, renderWithProviders } from "./test/utils";

const NOTE = "PageRank measures structural influence inside this citation graph.";

describe("App routing", () => {
  it("navigates between the dashboard and the papers browser", async () => {
    mockApi({
      "/api/analytics/summary": summary(),
      "/api/analytics/influential": { entity: "paper", metric: "pagerank", note: NOTE, papers: [], authors: [] },
      "/api/papers": page([paper({ title: "Listed Paper" })]),
    });
    renderWithProviders(<App />, "/");
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("link", { name: "Papers" }));
    expect(await screen.findByText("Listed Paper")).toBeInTheDocument();
  });

  it("shows a not-found page for unknown routes", async () => {
    mockApi({});
    renderWithProviders(<App />, "/does-not-exist");
    expect(await screen.findByText("Page not found")).toBeInTheDocument();
  });

  it("states the metric caveat in the footer on every page", async () => {
    mockApi({});
    renderWithProviders(<App />, "/does-not-exist");
    expect(await screen.findByText(/not measures of research quality/)).toBeInTheDocument();
  });
});
