import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { errorResponse, mockApi, renderWithProviders } from "../test/utils";
import { paper } from "../test/fixtures";
import { AuthorDetailPage } from "./AuthorDetailPage";
import { CommunityDetailPage } from "./CommunityDetailPage";
import { TopicDetailPage } from "./TopicDetailPage";
import { TopicsPage } from "./TopicsPage";

function at(path: string, pattern: string, element: React.ReactElement) {
  renderWithProviders(
    <Routes>
      <Route path={pattern} element={element} />
    </Routes>,
    path,
  );
}

describe("explorer pages", () => {
  it("lists topics, largest first", async () => {
    mockApi({
      "/api/topics": {
        items: [
          { id: "topic:a", name: "Small", paper_count: 1 },
          { id: "topic:b", name: "Large", paper_count: 9 },
        ],
        total: 2,
        page: 1,
        page_size: 100,
      },
    });
    renderWithProviders(<TopicsPage />);
    const links = await screen.findAllByRole("link");
    expect(links.map((l) => l.textContent)).toEqual(["Large9 papers", "Small1 paper"]);
  });

  it("shows a topic with related topics and papers", async () => {
    mockApi({
      "/api/topics/topic:1": {
        id: "topic:1",
        name: "Graph Learning",
        description: null,
        paper_count: 2,
        papers_per_year: { "2017": 1, "2019": 1 },
        top_papers: [paper({ title: "Top Topic Paper" })],
        top_authors: [{ id: "author:1", name: "Ann Author", paper_count: 2 }],
        related_topics: [{ id: "topic:2", name: "Attention", shared_papers: 3 }],
      },
    });
    at("/topics/topic:1", "/topics/:topicId", <TopicDetailPage />);
    expect(await screen.findByRole("heading", { name: "Graph Learning" })).toBeInTheDocument();
    expect(screen.getByText("Top Topic Paper")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Attention/ })).toHaveAttribute("href", "/topics/topic%3A2");
    expect(screen.getByRole("img", { name: /by publication year/ })).toBeInTheDocument();
  });

  it("shows an author with collaborators and a not-quality caveat", async () => {
    mockApi({
      "/api/authors/author:1": {
        id: "author:1",
        name: "Ann Author",
        orcid: null,
        openalex_id: null,
        institutions: [],
        papers: [paper({ title: "Her Paper" })],
        topics: [{ id: "topic:1", name: "Graph Learning", score: null }],
        collaborators: [{ id: "author:2", name: "Ben Builder", shared_papers: 2 }],
        metrics: { pagerank: 0.01, betweenness: null, in_degree: null, out_degree: null, community_id: "community:author:1" },
      },
    });
    at("/authors/author:1", "/authors/:authorId", <AuthorDetailPage />);
    expect(await screen.findByRole("heading", { name: "Ann Author" })).toBeInTheDocument();
    expect(screen.getByText("Her Paper")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ben Builder" })).toHaveAttribute("href", "/authors/author%3A2");
    expect(screen.getByText(/not the quality of the author/)).toBeInTheDocument();
  });

  it("shows a community with cross-community citation links", async () => {
    mockApi({
      "/api/communities/community:paper:1": {
        id: "community:paper:1",
        scope: "papers",
        rank: 1,
        size: 30,
        label: "Sequence models",
        algorithm: "louvain",
        computed_at: null,
        top_topics: ["Attention"],
        topics: [],
        institutions: [],
        papers_per_year: { "2017": 4 },
        top_papers: [paper({ title: "Community Paper" })],
        top_authors: [{ id: "author:1", name: "Ann Author", count: 3 }],
        connections: [{ community_id: "community:paper:2", label: "Graphs", citations_in: 2, citations_out: 5 }],
      },
    });
    at("/communities/community:paper:1", "/communities/:communityId", <CommunityDetailPage />);
    expect(await screen.findByRole("heading", { name: "Sequence models" })).toBeInTheDocument();
    expect(screen.getByText("Community Paper")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Graphs" })).toHaveAttribute("href", "/communities/community%3Apaper%3A2");
  });

  it("says when a topic does not exist", async () => {
    mockApi({
      "/api/topics/topic:x": () => errorResponse(404, "not_found", "no such topic"),
    });
    at("/topics/topic:x", "/topics/:topicId", <TopicDetailPage />);
    expect(await screen.findByText("Topic not found")).toBeInTheDocument();
  });
});
