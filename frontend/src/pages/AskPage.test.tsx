import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { errorResponse, mockApi, renderWithProviders } from "../test/utils";
import { paper } from "../test/fixtures";
import { AskPage } from "./AskPage";

const answer = {
  question: "What is attention?",
  answer: "Attention weights inputs [1]. It underpins transformers [2].",
  answerable: true,
  grounded: true,
  sources: [
    { n: 1, paper: paper({ id: "paper:1", title: "Attention Paper" }), role: "retrieved", score: 0.03, links_to_retrieved: 0, excerpt: "About weighting.", cited: true },
    { n: 2, paper: paper({ id: "paper:2", title: "Transformer Paper" }), role: "graph", score: null, links_to_retrieved: 2, excerpt: null, cited: true },
  ],
  relations: [{ source: 2, target: 1 }],
  retrieval: { mode: "hybrid", semantic_available: true, note: null, retrieved: 1, expanded: 1 },
  model: "gpt-4o-mini",
};

async function ask() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Question"), "What is attention?");
  await user.click(screen.getByRole("button", { name: "Ask" }));
}

describe("AskPage", () => {
  it("shows the answer with markers linking to numbered sources", async () => {
    mockApi({ "/api/ask": answer });
    renderWithProviders(<AskPage />);
    await ask();
    expect(await screen.findByText(/Attention weights inputs/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Source 1" })).toHaveAttribute("href", "#source-1");
    expect(screen.getByRole("link", { name: "Attention Paper" })).toHaveAttribute("href", "/papers/paper%3A1");
    expect(screen.getByText("Matched your question")).toBeInTheDocument();
    expect(screen.getByText(/Cited by or citing 2 matched/)).toBeInTheDocument();
    expect(screen.getByText("How the sources connect")).toBeInTheDocument();
  });

  it("warns when the answer is not grounded in a source", async () => {
    mockApi({ "/api/ask": { ...answer, grounded: false, answer: "Unsupported." } });
    renderWithProviders(<AskPage />);
    await ask();
    expect(await screen.findByText(/cites no source/)).toBeInTheDocument();
  });

  it("explains unanswerable questions", async () => {
    mockApi({ "/api/ask": { ...answer, answerable: false, grounded: false, answer: "Not covered." } });
    renderWithProviders(<AskPage />);
    await ask();
    expect(await screen.findByText(/do not contain enough/)).toBeInTheDocument();
  });

  it("renders model markup as plain text", async () => {
    mockApi({ "/api/ask": { ...answer, answer: "<img src=x onerror=alert(1)> [1]" } });
    const { container } = renderWithProviders(<AskPage />);
    await ask();
    await screen.findByText(/img src=x/);
    expect(container.querySelector("img")).toBeNull();
  });

  it("shows API errors such as an unavailable LLM", async () => {
    mockApi({ "/api/ask": () => errorResponse(503, "dependency_unavailable", "LLM_PROVIDER=openai but OPENAI_API_KEY is not set.") });
    renderWithProviders(<AskPage />);
    await ask();
    expect(await screen.findByText(/OPENAI_API_KEY/)).toBeInTheDocument();
  });
});
