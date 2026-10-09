import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { errorResponse, mockApi, renderWithProviders } from "../test/utils";
import { QueryPage } from "./QueryPage";

const result = {
  question: "top authors",
  answerable: true,
  message: null,
  cypher: "MATCH (a:Author) RETURN a.name AS author LIMIT 5",
  explanation: "Lists authors.",
  columns: ["author", "papers"],
  rows: [{ author: "Ada", papers: 3 }, { author: "Bo", papers: null }],
  row_count: 2,
  truncated: false,
  attempts: 2,
  model: "gpt-4o-mini",
};

async function run() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Question"), "top authors");
  await user.click(screen.getByRole("button", { name: "Run" }));
}

describe("QueryPage", () => {
  it("shows a table and the Cypher that produced it", async () => {
    mockApi({ "/api/query": result });
    renderWithProviders(<QueryPage />);
    await run();
    expect(await screen.findByRole("columnheader", { name: "author" })).toBeInTheDocument();
    expect(screen.getByText("Ada")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText(/MATCH \(a:Author\)/)).toBeInTheDocument();
    expect(screen.getByText(/after one rejected draft/)).toBeInTheDocument();
  });

  it("warns when results are truncated", async () => {
    mockApi({ "/api/query": { ...result, truncated: true } });
    renderWithProviders(<QueryPage />);
    await run();
    expect(await screen.findByText(/there may be more/)).toBeInTheDocument();
  });

  it("explains questions the schema cannot answer", async () => {
    mockApi({ "/api/query": { ...result, answerable: false, message: "No country data.", cypher: null } });
    renderWithProviders(<QueryPage />);
    await run();
    expect(await screen.findByText("No country data.")).toBeInTheDocument();
  });

  it("shows rejection errors", async () => {
    mockApi({ "/api/query": () => errorResponse(422, "validation_failed", "Could not produce a safe query") });
    renderWithProviders(<QueryPage />);
    await run();
    expect(await screen.findByText(/safe query/)).toBeInTheDocument();
  });
});
