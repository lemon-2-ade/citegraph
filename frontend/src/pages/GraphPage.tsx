import { useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useGraphNeighbourhood, useGraphOverview, usePaperCommunities } from "../api/queries";
import { ErrorState, Loading } from "../components/StateViews";
import { FitIcon, MinusIcon, PlusIcon } from "../components/Icons";
import { GraphCanvas, type GraphHandle } from "../graph/GraphCanvas";
import { CommunityLegend, YearLegend } from "../graph/GraphLegend";
import { SelectionPanel } from "../graph/SelectionPanel";
import {
  type ColorBy,
  communityColour,
  communityLegend,
  communityRanks,
  type SizeBy,
  yearRange,
} from "../graph/encode";
import { useTokens } from "../graph/useTokens";
import { formatCount, formatScore, paperTitle } from "../lib/format";

function clampInt(value: string | null, min: number, max: number, fallback: number): number {
  const n = Number(value);
  return Number.isInteger(n) && n >= min && n <= max ? n : fallback;
}

export function GraphPage() {
  const [params, setParams] = useSearchParams();
  const tokens = useTokens();
  const handle = useRef<GraphHandle>(null);

  const focus = params.get("focus");
  const limit = clampInt(params.get("limit"), 5, 300, focus ? 60 : 80);
  const depth = clampInt(params.get("depth"), 1, 2, 1) as 1 | 2;
  const sizeBy: SizeBy = params.get("size") === "cited_by" ? "cited_by" : "pagerank";
  const colorBy: ColorBy = params.get("color") === "year" ? "year" : "community";
  const [table, setTable] = useState(false);
  const [labels, setLabels] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);

  const overview = useGraphOverview(limit);
  const hood = useGraphNeighbourhood(focus, depth, limit);
  const active = focus ? hood : overview;
  const view = active.data;
  const communities = usePaperCommunities();

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v === null || v === "") next.delete(k);
      else next.set(k, v);
    }
    setParams(next, { replace: true });
  };

  const ranks = useMemo(
    () => communityRanks(view?.nodes ?? [], communities.data),
    [view, communities.data],
  );
  const legend = useMemo(() => communityLegend(view?.nodes ?? [], ranks, tokens), [view, ranks, tokens]);
  const [minYear, maxYear] = yearRange(view?.nodes ?? []);
  const selectedNode = view?.nodes.find((n) => n.id === selected) ?? null;
  const focusNode = view?.nodes.find((n) => n.id === focus) ?? null;

  const setFocus = (id: string | null) => {
    setSelected(id);
    update({ focus: id });
  };

  return (
    <div className="gx">
      <div className="gx-bar">
        <h1>Graph explorer</h1>
        <label className="gx-ctl">
          {focus ? "Papers" : "Top papers"}
          <input
            type="range"
            min={5}
            max={300}
            step={5}
            value={limit}
            onChange={(e) => update({ limit: e.target.value })}
            aria-label="Number of papers"
          />
          <output>{limit}</output>
        </label>
        {focus && (
          <div className="seg" role="group" aria-label="Neighbourhood depth">
            {[1, 2].map((d) => (
              <button key={d} type="button" aria-pressed={depth === d} onClick={() => update({ depth: String(d) })}>
                {d} hop{d > 1 ? "s" : ""}
              </button>
            ))}
          </div>
        )}
        <div className="gx-ctl">
          Size
          <div className="seg" role="group" aria-label="Size nodes by">
            <button type="button" aria-pressed={sizeBy === "pagerank"} onClick={() => update({ size: null })}>
              PageRank
            </button>
            <button type="button" aria-pressed={sizeBy === "cited_by"} onClick={() => update({ size: "cited_by" })}>
              Cited by
            </button>
          </div>
        </div>
        <div className="gx-ctl">
          Colour
          <div className="seg" role="group" aria-label="Colour nodes by">
            <button type="button" aria-pressed={colorBy === "community"} onClick={() => update({ color: null })}>
              Community
            </button>
            <button type="button" aria-pressed={colorBy === "year"} onClick={() => update({ color: "year" })}>
              Year
            </button>
          </div>
        </div>
        <label className="gx-ctl">
          <input type="checkbox" checked={labels} onChange={(e) => setLabels(e.target.checked)} /> Labels
        </label>
        <div className="seg" role="group" aria-label="View">
          <button type="button" aria-pressed={!table} onClick={() => setTable(false)}>
            Graph
          </button>
          <button type="button" aria-pressed={table} onClick={() => setTable(true)}>
            Table
          </button>
        </div>
        {!table && (
          <button type="button" className="btn btn-sm" onClick={() => handle.current?.relayout()}>
            Re-layout
          </button>
        )}
        {focus && (
          <button type="button" className="btn btn-sm" onClick={() => setFocus(null)}>
            Back to overview
          </button>
        )}
      </div>

      <div className="gx-stage">
        {active.isPending && (
          <div className="gx-table-wrap">
            <Loading label="Loading graph" />
          </div>
        )}
        {active.isError && (
          <div className="gx-table-wrap">
            <ErrorState error={active.error} onRetry={() => void active.refetch()} />
          </div>
        )}
        {view && view.nodes.length === 0 && (
          <div className="gx-table-wrap">
            <div className="card empty">
              <strong>Nothing to draw yet</strong>
              Load the sample data with <code>researchgraph seed</code>, then run <code>researchgraph analyze</code>.
            </div>
          </div>
        )}
        {view && view.nodes.length > 0 && !table && (
          <>
            <GraphCanvas
              ref={handle}
              view={view}
              sizeBy={sizeBy}
              colorBy={colorBy}
              communities={communities.data}
              selectedId={selected}
              onSelect={setSelected}
              onOpen={(id) => setFocus(id)}
              labelCount={labels ? 12 : 0}
            />
            <div className="gx-status chips">
              <span className="chip">
                {view.nodes.length} papers · {view.edges.length} citations
                {view.focus && ` · around “${paperTitle(focusNode?.title ?? null).slice(0, 40)}”`}
              </span>
              {view.truncated && <span className="chip">Showing the most influential {view.nodes.length} of {formatCount(view.total_papers)}</span>}
            </div>
            {colorBy === "community" ? (
              <CommunityLegend entries={legend} />
            ) : (
              <YearLegend min={minYear} max={maxYear} ramp={tokens.seq.slice(1)} />
            )}
            <div className="gx-zoom">
              <button type="button" className="btn btn-sm" aria-label="Zoom in" onClick={() => handle.current?.zoomIn()}>
                <PlusIcon />
              </button>
              <button type="button" className="btn btn-sm" aria-label="Zoom out" onClick={() => handle.current?.zoomOut()}>
                <MinusIcon />
              </button>
              <button type="button" className="btn btn-sm" aria-label="Fit to screen" onClick={() => handle.current?.fit()}>
                <FitIcon />
              </button>
            </div>
          </>
        )}
        {view && view.nodes.length > 0 && table && (
          <div className="gx-table-wrap">
            <table className="tbl">
              <caption className="sr-only">Papers shown in the graph</caption>
              <thead>
                <tr>
                  <th>Paper</th>
                  <th>Year</th>
                  <th>Community</th>
                  <th>Cited by</th>
                  <th>PageRank</th>
                </tr>
              </thead>
              <tbody>
                {view.nodes.map((n) => (
                  <tr key={n.id} aria-selected={n.id === selected}>
                    <td>
                      <Link to={`/papers/${encodeURIComponent(n.id)}`}>{paperTitle(n.title)}</Link>
                    </td>
                    <td>{n.year ?? "—"}</td>
                    <td>
                      <span className="dot" style={{ background: communityColour(n.community_id, ranks, tokens), marginRight: 6 }} aria-hidden="true" />
                      {n.community_label ?? "—"}
                    </td>
                    <td>{formatCount(n.cited_by_in_graph)}</td>
                    <td>{formatScore(n.pagerank)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <aside className="gx-side" aria-label="Details">
        {selectedNode ? (
          <SelectionPanel
            node={selectedNode}
            focused={selectedNode.id === focus}
            onFocus={setFocus}
            colour={communityColour(selectedNode.community_id, ranks, tokens)}
          />
        ) : (
          <div className="stack">
            <h2>{focus ? "Citation neighbourhood" : "Citation overview"}</h2>
            <p className="small muted">
              {view?.note ??
                "Each circle is a paper; arrows point from the citing paper to the paper it cites."}
            </p>
            <ul className="small muted" style={{ paddingLeft: 18, margin: 0 }}>
              <li>Click a paper for details.</li>
              <li>Double-click a paper (or use “Focus neighbourhood”) to explore its citations.</li>
              <li>Size shows {sizeBy === "pagerank" ? "PageRank" : "citations received in this graph"}; neither measures quality.</li>
            </ul>
            <Link className="btn btn-sm" to="/papers">
              Browse papers as a list
            </Link>
          </div>
        )}
      </aside>
    </div>
  );
}
