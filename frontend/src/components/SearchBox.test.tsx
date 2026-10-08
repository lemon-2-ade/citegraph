import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { mockApi, renderWithProviders } from "../test/utils";
import { SearchBox } from "./SearchBox";

describe("SearchBox", () => {
  it("shows grouped results linking to each entity", async () => {
    mockApi({
      "/api/search": {
        query: "atten",
        papers: [{ kind: "paper", id: "paper:1", title: "Attention Is All You Need", subtitle: "A · 2017", score: 2 }],
        authors: [{ kind: "author", id: "author:1", title: "Ann Author", subtitle: "3 papers", score: 1 }],
        topics: [],
      },
    });
    renderWithProviders(<SearchBox />);
    await userEvent.type(screen.getByRole("searchbox"), "atten");
    const paper = await screen.findByRole("link", { name: /Attention Is All You Need/ });
    expect(paper).toHaveAttribute("href", "/papers/paper%3A1");
    expect(screen.getByRole("link", { name: /Ann Author/ })).toHaveAttribute("href", "/authors/author%3A1");
    expect(screen.getByText("Authors")).toBeInTheDocument();
    expect(screen.queryByText("Topics")).not.toBeInTheDocument();
  });

  it("does not search for a single character and reports no matches", async () => {
    const { seen } = mockApi({ "/api/search": { query: "zzz", papers: [], authors: [], topics: [] } });
    renderWithProviders(<SearchBox />);
    await userEvent.type(screen.getByRole("searchbox"), "z");
    expect(seen).toHaveLength(0);
    await userEvent.type(screen.getByRole("searchbox"), "zz");
    expect(await screen.findByText(/No matches for/)).toBeInTheDocument();
  });
});
