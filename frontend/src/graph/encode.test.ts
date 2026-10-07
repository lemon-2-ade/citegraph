import {
  communityColour,
  communityLegend,
  communityRanks,
  labelledIds,
  maxMetric,
  nodeRadius,
  shortTitle,
  type Tokens,
  yearColour,
  yearRange,
} from "./encode";
import type { GraphNode } from "./types";

const tokens: Tokens = {
  series: ["s1", "s2", "s3", "s4", "s5", "s6", "s7"],
  other: "other",
  seq: ["q1", "q2", "q3", "q4", "q5", "q6"],
  ink: "ink",
  ink2: "ink2",
  surface: "surface",
  plane: "plane",
  axis: "axis",
  accent: "accent",
};

const node = (id: string, extra: Partial<GraphNode> = {}): GraphNode => ({
  id,
  title: `Paper ${id}`,
  year: 2018,
  pagerank: 0.01,
  cited_by_in_graph: 1,
  community_id: null,
  community_label: null,
  is_stub: false,
  authors: [],
  ...extra,
});

describe("nodeRadius", () => {
  it("is monotonic, bounded, and uses area scaling", () => {
    expect(nodeRadius(0, 10)).toBe(7);
    expect(nodeRadius(null, 10)).toBe(7);
    expect(nodeRadius(10, 10)).toBe(26);
    expect(nodeRadius(100, 10)).toBe(26); // clamped
    const quarter = nodeRadius(2.5, 10);
    expect(quarter).toBeCloseTo(7 + 19 * 0.5, 5); // sqrt(0.25) = 0.5
    expect(nodeRadius(5, 10)).toBeGreaterThan(quarter);
  });

  it("copes with an all-zero view", () => {
    expect(maxMetric([node("a", { pagerank: null })], "pagerank")).toBe(0);
    expect(nodeRadius(1, 0)).toBe(7);
  });
});

describe("community colours", () => {
  const communities = [
    { id: "c-big", rank: 1 },
    { id: "c-mid", rank: 2 },
    { id: "c-far", rank: 9 },
  ];

  it("follows the community's global rank, not what is on screen", () => {
    const ranks = communityRanks([], communities);
    expect(communityColour("c-big", ranks, tokens)).toBe("s1");
    expect(communityColour("c-mid", ranks, tokens)).toBe("s2");
    // The same community keeps its colour in any subgraph.
    const sub = communityRanks([node("x", { community_id: "c-mid" })], communities);
    expect(communityColour("c-mid", sub, tokens)).toBe("s2");
  });

  it("folds small, unknown and missing communities into the neutral colour", () => {
    const ranks = communityRanks([], communities);
    expect(communityColour("c-far", ranks, tokens)).toBe("other");
    expect(communityColour("unknown", ranks, tokens)).toBe("other");
    expect(communityColour(null, ranks, tokens)).toBe("other");
  });

  it("falls back to in-view sizes when the community list is unavailable", () => {
    const nodes = [
      node("a", { community_id: "x" }),
      node("b", { community_id: "y" }),
      node("c", { community_id: "y" }),
    ];
    const ranks = communityRanks(nodes, undefined);
    expect(ranks.get("y")).toBe(1);
    expect(ranks.get("x")).toBe(2);
  });

  it("builds a legend with counts, rank order and an Other entry", () => {
    const ranks = communityRanks([], communities);
    const nodes = [
      node("a", { community_id: "c-mid", community_label: "Graph Learning" }),
      node("b", { community_id: "c-big", community_label: "Transformers" }),
      node("c", { community_id: "c-big", community_label: "Transformers" }),
      node("d", { community_id: null }),
      node("e", { community_id: "c-far" }),
    ];
    const legend = communityLegend(nodes, ranks, tokens);
    expect(legend.map((l) => [l.label, l.count, l.colour])).toEqual([
      ["Transformers", 2, "s1"],
      ["Graph Learning", 1, "s2"],
      ["Other / unassigned", 2, "other"],
    ]);
  });
});

describe("year colours", () => {
  it("maps old to new across steps 2-6 and never uses step 1", () => {
    expect(yearColour(2010, 2010, 2020, tokens)).toBe("q2");
    expect(yearColour(2020, 2010, 2020, tokens)).toBe("q6");
    expect(yearColour(2015, 2010, 2020, tokens)).toBe("q4");
    expect(yearColour(null, 2010, 2020, tokens)).not.toBe("q1");
    expect(yearColour(2018, 2018, 2018, tokens)).not.toBe("q1");
  });

  it("ignores missing years when computing the range", () => {
    expect(yearRange([node("a", { year: 2010 }), node("b", { year: null }), node("c", { year: 2020 })])).toEqual([
      2010, 2020,
    ]);
    expect(yearRange([node("a", { year: null })])).toEqual([0, 0]);
  });
});

describe("labels", () => {
  it("shortens long titles and names stubs", () => {
    expect(shortTitle("A".repeat(60), 20)).toHaveLength(20);
    expect(shortTitle(null)).toBe("Untitled (stub)");
    expect(shortTitle("Short")).toBe("Short");
  });

  it("labels only the k largest nodes", () => {
    const nodes = [
      node("a", { pagerank: 0.1 }),
      node("b", { pagerank: 0.5 }),
      node("c", { pagerank: 0.3 }),
    ];
    expect(labelledIds(nodes, "pagerank", 2)).toEqual(new Set(["b", "c"]));
  });
});
