import type { GraphNode } from "./types";

/** Colour tokens read from the CSS custom properties, so canvas drawing follows the theme. */
export interface Tokens {
  /** Categorical slots 1-7, in fixed order. */
  series: string[];
  other: string;
  /** Sequential ramp, low to high salience. */
  seq: string[];
  ink: string;
  ink2: string;
  surface: string;
  plane: string;
  axis: string;
  accent: string;
}

export const MAX_COMMUNITY_COLOURS = 7;

const read = (style: CSSStyleDeclaration, name: string, fallback: string) =>
  style.getPropertyValue(name).trim() || fallback;

export function readTokens(el: Element = document.documentElement): Tokens {
  const s = getComputedStyle(el);
  return {
    series: [1, 2, 3, 4, 5, 6, 7].map((i) => read(s, `--series-${i}`, "#2a78d6")),
    other: read(s, "--series-other", "#898781"),
    seq: [1, 2, 3, 4, 5, 6].map((i) => read(s, `--seq-${i}`, "#3987e5")),
    ink: read(s, "--ink", "#0b0b0b"),
    ink2: read(s, "--ink-2", "#52514e"),
    surface: read(s, "--surface", "#fcfcfb"),
    plane: read(s, "--plane", "#f9f9f7"),
    axis: read(s, "--axis", "#c3c2b7"),
    accent: read(s, "--accent", "#2a78d6"),
  };
}

export type SizeBy = "pagerank" | "cited_by";
export type ColorBy = "community" | "year";

/** Radius in px on a square-root scale, so area (not diameter) tracks the metric. */
export function nodeRadius(value: number | null | undefined, max: number, min = 7, top = 26): number {
  if (value == null || value <= 0 || max <= 0) return min;
  return min + (top - min) * Math.sqrt(Math.min(value / max, 1));
}

export function metricOf(node: GraphNode, sizeBy: SizeBy): number {
  return sizeBy === "pagerank" ? (node.pagerank ?? 0) : node.cited_by_in_graph;
}

export function maxMetric(nodes: readonly GraphNode[], sizeBy: SizeBy): number {
  return nodes.reduce((m, n) => Math.max(m, metricOf(n, sizeBy)), 0);
}

/**
 * Community ranks (1 = largest) from the global community list, so a community keeps its
 * colour whatever subgraph is on screen. Falls back to ranking by size within the view.
 */
export function communityRanks(
  nodes: readonly GraphNode[],
  communities: readonly { id: string; rank: number }[] | undefined,
): Map<string, number> {
  const ranks = new Map<string, number>();
  if (communities && communities.length > 0) {
    for (const c of communities) ranks.set(c.id, c.rank);
    return ranks;
  }
  const counts = new Map<string, number>();
  for (const n of nodes) if (n.community_id) counts.set(n.community_id, (counts.get(n.community_id) ?? 0) + 1);
  [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .forEach(([id], i) => ranks.set(id, i + 1));
  return ranks;
}

export function communityColour(
  communityId: string | null | undefined,
  ranks: ReadonlyMap<string, number>,
  tokens: Tokens,
): string {
  const rank = communityId ? ranks.get(communityId) : undefined;
  if (rank === undefined || rank > MAX_COMMUNITY_COLOURS) return tokens.other;
  return tokens.series[rank - 1] ?? tokens.other;
}

/** Year -> a step of the one-hue ramp (steps 2-6; step 1 is too close to the surface). */
export function yearColour(year: number | null | undefined, min: number, max: number, tokens: Tokens): string {
  const steps = tokens.seq.slice(1);
  if (year == null || max <= min) return steps[Math.floor(steps.length / 2)] ?? tokens.other;
  const t = Math.min(Math.max((year - min) / (max - min), 0), 1);
  return steps[Math.round(t * (steps.length - 1))] ?? tokens.other;
}

export function yearRange(nodes: readonly GraphNode[]): [number, number] {
  const years = nodes.map((n) => n.year).filter((y): y is number => y != null);
  if (years.length === 0) return [0, 0];
  return [Math.min(...years), Math.max(...years)];
}

export interface LegendEntry {
  key: string;
  label: string;
  count: number;
  colour: string;
}

/** One entry per colour actually shown: the visible communities, then "Other". */
export function communityLegend(
  nodes: readonly GraphNode[],
  ranks: ReadonlyMap<string, number>,
  tokens: Tokens,
): LegendEntry[] {
  const groups = new Map<string, LegendEntry>();
  let other = 0;
  for (const n of nodes) {
    const rank = n.community_id ? ranks.get(n.community_id) : undefined;
    if (!n.community_id || rank === undefined || rank > MAX_COMMUNITY_COLOURS) {
      other += 1;
      continue;
    }
    const entry = groups.get(n.community_id);
    if (entry) entry.count += 1;
    else
      groups.set(n.community_id, {
        key: n.community_id,
        label: n.community_label ?? `Community ${rank}`,
        count: 1,
        colour: communityColour(n.community_id, ranks, tokens),
      });
  }
  const entries = [...groups.values()].sort(
    (a, b) => (ranks.get(a.key) ?? 99) - (ranks.get(b.key) ?? 99),
  );
  if (other > 0) entries.push({ key: "other", label: "Other / unassigned", count: other, colour: tokens.other });
  return entries;
}

export function shortTitle(title: string | null, max = 34): string {
  const text = title && title.trim() ? title.trim() : "Untitled (stub)";
  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text;
}

/** Ids of the k largest nodes, which keep a permanent label. */
export function labelledIds(nodes: readonly GraphNode[], sizeBy: SizeBy, k: number): Set<string> {
  return new Set(
    [...nodes]
      .sort((a, b) => metricOf(b, sizeBy) - metricOf(a, sizeBy) || a.id.localeCompare(b.id))
      .slice(0, k)
      .map((n) => n.id),
  );
}
