import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { mockApi, renderWithProviders } from "../test/utils";
import { page, paper } from "../test/fixtures";
import { PapersPage } from "./PapersPage";

describe("PapersPage", () => {
  it("lists papers with their in-graph citation counts", async () => {
    mockApi({
      "/api/papers": page([paper({ title: "First Paper" }), paper({ id: "paper:2", title: "Second Paper", is_stub: true })], 2),
    });
    renderWithProviders(<PapersPage />, "/papers");
    expect(await screen.findByText("First Paper")).toBeInTheDocument();
    expect(screen.getByText("Second Paper")).toBeInTheDocument();
    expect(screen.getByText("stub")).toBeInTheDocument();
    expect(screen.getByText("2 papers")).toBeInTheDocument();
  });

  it("sends the year filter to the API and resets to the first page", async () => {
    const { seen } = mockApi({ "/api/papers": page([paper()], 1) });
    renderWithProviders(<PapersPage />, "/papers?page=3");
    await screen.findByText(/papers$/);

    await userEvent.type(screen.getByLabelText("From year"), "2018");
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => {
      const last = seen.at(-1);
      expect(last?.searchParams.get("year_from")).toBe("2018");
      expect(last?.searchParams.get("page")).toBe("1");
    });
  });

  it("ignores out-of-range years from the URL instead of sending them", async () => {
    const { seen } = mockApi({ "/api/papers": page([paper()], 1) });
    renderWithProviders(<PapersPage />, "/papers?year_from=99999&sort=bogus");
    await screen.findByText(/papers$/);
    const first = seen[0];
    expect(first?.searchParams.has("year_from")).toBe(false);
    expect(first?.searchParams.get("sort")).toBe("year");
  });

  it("shows an empty state when nothing matches", async () => {
    mockApi({ "/api/papers": page([], 0) });
    renderWithProviders(<PapersPage />, "/papers?year_from=1990");
    expect(await screen.findByText("No papers match these filters")).toBeInTheDocument();
  });

  it("pages through results", async () => {
    const { seen } = mockApi({
      "/api/papers": (url) =>
        new Response(JSON.stringify(page([paper({ title: `Page ${url.searchParams.get("page")}` })], 45, Number(url.searchParams.get("page")))), {
          headers: { "content-type": "application/json" },
        }),
    });
    renderWithProviders(<PapersPage />, "/papers");
    expect(await screen.findByText("Page 1")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Page 2")).toBeInTheDocument();
    expect(seen.at(-1)?.searchParams.get("page")).toBe("2");
  });
});
