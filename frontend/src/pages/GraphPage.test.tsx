import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { GraphView } from "../graph/types";
import { mockApi, renderWithProviders } from "../test/utils";
import { GraphPage } from "./GraphPage";

vi.mock("../graph/GraphCanvas", () => ({
  GraphCanvas: () => <div data-testid="graph-canvas" />, // jsdom has no canvas
}));

const view: GraphView = {
  nodes: [
    {
      id: "paper:1",
      title: "Attention Mechanisms",
      year: 2017,
      pagerank: 0.05,
      cited_by_in_graph: 4,
      community_id: "c:1",
      community_label: "Sequence models",
      is_stub: false,
      authors: ["Ann Author"],
    },
    {
      id: "paper:2",
      title: "Graph Networks",
      year: 2019,
      pagerank: 0.02,
      cited_by_in_graph: 1,
      community_id: null,
      community_label: null,
      is_stub: false,
      authors: [],
    },
  ],
  edges: [{ source: "paper:2", target: "paper:1", type: "CITES" }],
  focus: null,
  truncated: true,
  total_papers: 105,
  note: "Top papers by PageRank.",
};

const routes = {
  "/api/graph/overview": view,
  "/api/communities": [
    { id: "c:1", rank: 1, size: 40, label: "Sequence models", algorithm: "louvain", scope: "papers", computed_at: null, top_topics: [] },
  ],
};

describe("GraphPage", () => {
  it("renders the graph with a legend and a truncation notice", async () => {
    mockApi(routes);
    renderWithProviders(<GraphPage />);
    expect(await screen.findByTestId("graph-canvas")).toBeInTheDocument();
    expect(screen.getByText(/2 papers · 1 citations/)).toBeInTheDocument();
    expect(screen.getByText(/Showing the most influential 2 of 105/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Legend: research communities/)).toHaveTextContent("Sequence models");
    expect(screen.getByLabelText(/Legend: research communities/)).toHaveTextContent("Other / unassigned");
  });

  it("offers an accessible table view of the same papers", async () => {
    mockApi(routes);
    renderWithProviders(<GraphPage />);
    await screen.findByTestId("graph-canvas");
    await userEvent.click(screen.getByRole("button", { name: "Table" }));
    expect(screen.getByRole("link", { name: "Attention Mechanisms" })).toHaveAttribute("href", "/papers/paper%3A1");
    expect(screen.getByRole("link", { name: "Graph Networks" })).toBeInTheDocument();
    expect(screen.queryByTestId("graph-canvas")).not.toBeInTheDocument();
  });

  it("explains how to load data when there is nothing to draw", async () => {
    mockApi({ ...routes, "/api/graph/overview": { ...view, nodes: [], edges: [], truncated: false } });
    renderWithProviders(<GraphPage />);
    expect(await screen.findByText("Nothing to draw yet")).toBeInTheDocument();
  });
});
